"""Passive, bounded subdomain discovery with per-source provenance.

Evidence in an index/certificate is not proof of a currently resolving host.
No discovered hostname is contacted by this module.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from core.dns_lookup import validate_name
from lib.http import IntegrationError, get_json, get_text
import settings

SOURCES = ("crt.sh", "CertSpotter", "HackerTarget", "subfinder", "amass", "assetfinder")
MAX_NAMES = 20000
MAX_OUTPUT = 10 * 1024 * 1024
MAX_PAGES = 5
PROJECT = Path(__file__).resolve().parents[1]


def offline():
    return os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}


def validate_domain(domain):
    value = validate_name(domain, allow_underscore=False)
    if "." not in value or value.rsplit(".", 1)[1].isdigit():
        raise ValueError("Informe um domínio completo, por exemplo example.com.")
    return value


def find_tool(name):
    if name not in SOURCES[3:]:
        raise ValueError("Ferramenta desconhecida.")
    filename = name + (".exe" if os.name == "nt" else "")
    local = PROJECT / ".tools" / name / filename
    found = str(local) if local.is_file() else shutil.which(filename)
    if not found:
        return None
    path = Path(found).resolve()
    if os.name == "nt" and path.suffix.lower() != ".exe":
        return None
    return str(path) if path.is_file() else None


def _result(source):
    return {"source": source, "status": "ok", "message": "", "names": {}, "wildcards": {}, "truncated": False}


def _add(result, domain, candidate, provider=None):
    if not isinstance(candidate, str) or len(candidate) > 255:
        return
    candidate = candidate.strip()
    wildcard = candidate.startswith("*.")
    try:
        name = validate_domain(candidate[2:] if wildcard else candidate)
    except ValueError:
        return
    if name != domain and not name.endswith("." + domain):
        return
    if name == domain and not wildcard:
        return  # Apex is not a subdomain.
    bucket = result["wildcards"] if wildcard else result["names"]
    key = "*." + name if wildcard else name
    if key not in bucket and len(result["names"]) + len(result["wildcards"]) >= MAX_NAMES:
        result["truncated"] = True
        return
    origin = result["source"]
    if isinstance(provider, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", provider):
        origin += ":" + provider.lower()
    bucket.setdefault(key, set()).add(origin)


def _crtsh(domain, result):
    rows = get_json("https://crt.sh/", params={"q": "%." + domain, "output": "json"})
    if not isinstance(rows, list):
        raise IntegrationError("Resposta inesperada.", code="invalid_response")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name_value"), str):
            raise IntegrationError("Resposta inesperada.", code="invalid_response")
        for name in row["name_value"].splitlines():
            _add(result, domain, name)


def _certspotter(domain, result):
    params = {"domain": domain, "include_subdomains": "true", "expand": "dns_names"}
    key = os.environ.get("CERTSPOTTER_API_KEY", "").strip()
    headers = {"Authorization": "Bearer " + key} if key else None
    after = None
    for _ in range(MAX_PAGES):
        rows = get_json("https://api.certspotter.com/v1/issuances", params=dict(params), headers=headers)
        if not isinstance(rows, list):
            raise IntegrationError("Resposta inesperada.", code="invalid_response")
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("dns_names"), list):
                raise IntegrationError("Resposta inesperada.", code="invalid_response")
            for name in row["dns_names"]:
                _add(result, domain, name)
        cursor = rows[-1].get("id")
        if not isinstance(cursor, str) or not cursor or len(cursor) > 256 or cursor == after:
            raise IntegrationError("Paginação inválida.", code="invalid_response")
        after = cursor
        params["after"] = cursor
    result.update(status="partial", truncated=True, message="Limite de 5 páginas alcançado.")


def _hackertarget(domain, result):
    key = os.environ.get("HACKERTARGET_API_KEY", "").strip()
    headers = {"X-API-Key": key} if key else None
    text = get_text("https://api.hackertarget.com/hostsearch/", params={"q": domain}, headers=headers)
    lines = text.strip().splitlines()
    if not lines or text.strip().lower() in {"no records found", "no results found"}:
        return
    for line in lines:
        parts = line.split(",")
        if len(parts) != 2:
            # Quota/errors may arrive with HTTP 200. Never call them an empty result.
            raise IntegrationError("Serviço retornou erro ou formato inesperado.", code="provider_error")
        _add(result, domain, parts[0])
    result["message"] = "Índice de hosts; endereços históricos não são verificação DNS atual."
    if not key and len(lines) >= 50:
        result.update(status="partial", truncated=True, message="Possível limite gratuito de 50 registros.")


def _run_process(command, timeout, directory, *, include_stderr=False):
    """File-backed capture, capped while running; never interpolate a shell command."""
    with tempfile.TemporaryFile(dir=directory) as output, tempfile.TemporaryFile(dir=directory) as errors:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                       shell=False, cwd=directory,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            return "error", "", "Não foi possível iniciar o executável."
        started = time.monotonic()
        status, message = "ok", ""
        try:
            while process.poll() is None:
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT or os.fstat(errors.fileno()).st_size > MAX_OUTPUT:
                    status, message = "partial", "Limite de saída do executável alcançado."
                    break
                if time.monotonic() - started >= timeout:
                    status, message = "partial", "Timeout; resultados já recebidos foram preservados."
                    break
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        if status == "ok" and process.returncode != 0:
            status, message = "error", "Executável terminou com erro; saída de diagnóstico omitida."
        output.seek(0)
        data = output.read(MAX_OUTPUT + 1)
        if len(data) > MAX_OUTPUT:
            status, message = "partial", "Limite de saída do executável alcançado."
            data = data[:MAX_OUTPUT].rsplit(b"\n", 1)[0]
        if include_stderr:
            errors.seek(0)
            data += b"\n" + errors.read(MAX_OUTPUT)
        return status, data.decode("utf-8", errors="replace"), message


def _provider_config():
    configured = os.environ.get("SUBFINDER_PROVIDER_CONFIG")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise ValueError("SUBFINDER_PROVIDER_CONFIG deve apontar para um arquivo existente.")
        return path
    folder = Path(os.environ.get("APPDATA", str(Path.home() / ".config")))
    path = folder / "subfinder" / "provider-config.yaml"
    return path if path.is_file() else None


def _cli(domain, result, timeout):
    name = result["source"]
    binary = find_tool(name)
    if not binary:
        result.update(status="missing", message="Executável opcional não instalado.")
        return
    # Keep tool output/config/database in the private data folder.
    root = settings.data_directory().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="subdomains-", dir=root) as temporary:
        directory = Path(temporary)
        if name == "subfinder":
            config = directory / "config.yaml"
            config.write_text("{}\n", encoding="utf-8")
            providers = _provider_config()
            if providers is None:
                providers = directory / "providers.yaml"
                providers.write_text("{}\n", encoding="utf-8")
            command = [binary, "-d", domain, "-all", "-silent", "-nc", "-oJ", "-cs", "-duc",
                       "-rl", "5", "-timeout", "15", "-max-time", str(max(1, (timeout - 15) // 60)),
                       "-rsr", str(2 * 1024 * 1024), "-mr", str(MAX_NAMES),
                       "-config", str(config), "-pc", str(providers),
                       "-es", "crtsh,certspotter,hackertarget"]
        elif name == "amass":
            status, help_text, _ = _run_process([binary, "enum", "-h"], 5, directory, include_stderr=True)
            if status == "partial" or not re.search(r"(?m)^\s*-{1,2}passive(?:\s|$)", help_text):
                result.update(status="unsupported", message="Versão sem modo passivo compatível; não executada.")
                return
            command = [binary, "enum", "-passive", "-d", domain, "-nocolor", "-dir", str(directory)]
        else:
            command = [binary, "--subs-only", domain]
        status, output, message = _run_process(command, timeout, directory)
        result.update(status=status, message=message)
        malformed = False
        for line in output.splitlines():
            if not line.strip():
                continue
            if name == "subfinder":
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    malformed = True
                    continue
                if not isinstance(row, dict) or not isinstance(row.get("host"), str):
                    malformed = True
                    continue
                providers = row.get("sources", [row.get("source")])
                if not isinstance(providers, list) or not providers:
                    providers = [None]
                for provider in providers[:100]:
                    _add(result, domain, row.get("host"), provider)
            else:
                # Some Amass versions render graph edges instead of plain names.
                candidate = line.split(" (FQDN)", 1)[0] if name == "amass" else line
                _add(result, domain, candidate)
        if malformed and result["status"] == "ok":
            result.update(status="partial" if result["names"] or result["wildcards"] else "error",
                          message="Saída JSONL do executável contém registros inválidos.")
        if status == "error" and (result["names"] or result["wildcards"]):
            result["status"] = "partial"


def _source(source, domain, timeout):
    result = _result(source)
    try:
        if source in SOURCES[3:]:
            _cli(domain, result, timeout)
        else:
            {"crt.sh": _crtsh, "CertSpotter": _certspotter, "HackerTarget": _hackertarget}[source](domain, result)
    except IntegrationError as exc:
        result.update(status="partial" if result["names"] or result["wildcards"] else "error",
                      message="Consulta não concluída: " + (exc.code if re.fullmatch(r"[a-z0-9_]+", exc.code) else "error"))
    except (OSError, ValueError):
        result.update(status="partial" if result["names"] or result["wildcards"] else "error",
                      message="Falha de configuração ou execução da fonte.")
    if result["truncated"] and result["status"] == "ok":
        result.update(status="partial", message="Limite de nomes por fonte alcançado.")
    return result


def discover(domain, *, timeout=90, sources=SOURCES):
    domain = validate_domain(domain)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 10 <= timeout <= 300:
        raise ValueError("Timeout dos executáveis deve ser de 10 a 300 segundos.")
    if (not isinstance(sources, (tuple, list)) or not sources or any(not isinstance(s, str) or s not in SOURCES for s in sources)
            or len(sources) != len(set(sources))):
        raise ValueError("Seleção de fontes inválida.")
    report = {"domain": domain, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "passive", "dns_verified": False, "cli_timeout_seconds": timeout,
              "limits": {"names_per_source": MAX_NAMES, "certspotter_pages": MAX_PAGES,
                         "http_bytes_per_response": 2 * 1024 * 1024},
              "status": "offline" if offline() else "completed", "sources": [], "hosts": [], "wildcards": []}
    if offline():
        report["sources"] = [{"source": s, "status": "offline", "message": "Consulta desativada.",
                              "count": 0, "wildcard_count": 0, "truncated": False} for s in sources]
        return report
    merged, wildcards, results = {}, {}, {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_source, source, domain, timeout): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source] = future.result()
            except Exception:
                result = _result(source)
                result.update(status="error", message="Falha interna isolada nesta fonte.")
                results[source] = result
    for source in sources:
        result = results[source]
        for bucket, target in (("names", merged), ("wildcards", wildcards)):
            for name, origins in result[bucket].items():
                target.setdefault(name, set()).update(origins)
        report["sources"].append({"source": source, "status": result["status"], "message": result["message"],
                                  "count": len(result["names"]), "wildcard_count": len(result["wildcards"]),
                                  "truncated": result["truncated"]})
    report["hosts"] = [{"hostname": name, "sources": sorted(origins), "dns_status": "not_checked"}
                       for name, origins in sorted(merged.items())]
    report["wildcards"] = [{"pattern": name, "sources": sorted(origins)} for name, origins in sorted(wildcards.items())]
    statuses = [item["status"] for item in report["sources"]]
    if all(status in {"error", "missing", "unsupported"} for status in statuses):
        report["status"] = "unavailable"
    elif any(status != "ok" for status in statuses):
        report["status"] = "partial"
    return report


def export_report(report, format="json", *, directory=None):
    if format not in {"csv", "json"}:
        raise ValueError("Formato deve ser CSV ou JSON.")
    root = Path(directory).expanduser().resolve() if directory else settings.data_directory().resolve()
    folder = root / "subdomains"
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise ValueError("Pasta de exportação inválida.")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = folder / ("subdomains_" + uuid.uuid4().hex + "." + format)
    created = False
    try:
        with destination.open("x", encoding="utf-8-sig" if format == "csv" else "utf-8", newline="") as output:
            created = True
            try:
                destination.chmod(0o600)
            except OSError:
                pass
            if format == "json":
                json.dump(report, output, ensure_ascii=False, indent=2)
            else:
                writer = csv.writer(output)
                writer.writerow(["kind", "domain", "timestamp_utc", "value", "sources", "status", "detail"])
                writer.writerow(["report", report["domain"], report["timestamp_utc"], "", "", report["status"],
                                 json.dumps({key: report[key] for key in ("mode", "dns_verified", "cli_timeout_seconds", "limits")}, ensure_ascii=False)])
                for host in report["hosts"]:
                    writer.writerow(["host", report["domain"], report["timestamp_utc"], host["hostname"], ";".join(host["sources"]), host["dns_status"], ""])
                for item in report["wildcards"]:
                    writer.writerow(["wildcard", report["domain"], report["timestamp_utc"], item["pattern"], ";".join(item["sources"]), "certificate_pattern", "Não comprova host concreto."])
                for item in report["sources"]:
                    writer.writerow(["source", report["domain"], report["timestamp_utc"], item["source"], "", item["status"],
                                     json.dumps({key: value for key, value in item.items() if key not in ("source", "status")}, ensure_ascii=False)])
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        if created:
            destination.unlink(missing_ok=True)
        raise ValueError("Não foi possível gravar o relatório na pasta privada.") from None
    return destination


def show_sources():
    from terminaltables import AsciiTable
    rows = [["Fonte", "Disponibilidade"]]
    rows.extend([[source, "HTTPS; disponibilidade/quota verificada na consulta"] for source in SOURCES[:3]])
    rows.extend([[source, "Instalado (compatibilidade verificada na consulta)" if find_tool(source) else "Opcional; não instalado"] for source in SOURCES[3:]])
    print(AsciiTable(rows).table)
    print("Chaves opcionais: CERTSPOTTER_API_KEY, HACKERTARGET_API_KEY.")
    print("Subfinder: fontes com chave usam SUBFINDER_PROVIDER_CONFIG ou a configuração padrão do usuário.")


def interactive_discovery():
    from terminaltables import AsciiTable
    if offline():
        print("Modo offline: nenhuma fonte externa ou executável foi consultado.")
        return
    domain = validate_domain(input("Domínio (sem https://): ").strip())
    raw = input("Timeout por executável em segundos [90; 10–300]: ").strip()
    timeout = int(raw) if raw else 90
    print("Consultando fontes em paralelo. CertSpotter: até 5 páginas; HTTP: limites próprios de tempo/tamanho.")
    report = discover(domain, timeout=timeout)
    print(f"Estado: {report['status']} | {len(report['hosts'])} subdomínios únicos | {len(report['wildcards'])} padrões wildcard")
    rows = [["Subdomínio", "Fontes"]]
    rows.extend([[item["hostname"], ", ".join(item["sources"])] for item in report["hosts"][:200]])
    if report["hosts"]:
        print(AsciiTable(rows).table)
    else:
        print("Nenhum nome concreto retornado pelas fontes consultadas. Isso não comprova ausência de subdomínios.")
    if len(report["hosts"]) > 200:
        print("Tela limitada a 200 nomes. As exportações contêm todos os nomes obtidos.")
    for source in report["sources"]:
        print(f"[{source['status']}] {source['source']}: {source['count']} nomes; {source['wildcard_count']} padrões. {source['message']}")
    print("Evidência passiva: não confirma DNS atual, serviço ativo ou propriedade. Wildcards não são hosts concretos.")
    choice = input("Exportar [j] JSON / [c] CSV / [a] ambos / Enter pular: ").strip().lower()
    formats = {"j": ("json",), "c": ("csv",), "a": ("json", "csv"), "": ()}
    if choice not in formats:
        raise ValueError("Exportação não realizada: opção inválida.")
    for format in formats[choice]:
        print(f"Exportado: {export_report(report, format)}")
