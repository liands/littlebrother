"""Native route diagnostics with validated arguments and private local exports."""
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime
import io
import ipaddress
import locale
import os
from pathlib import Path
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

import settings

MAX_HOPS = 64
MAX_TIMEOUT = 180
MAX_OUTPUT = 1024 * 1024


class TraceError(ValueError):
    """Expected validation, platform or native diagnostic failure."""


@dataclass(frozen=True)
class Hop:
    number: int
    addresses: tuple[str, ...]
    latencies_ms: tuple[str, ...]
    markers: tuple[str, ...] = ()

    @property
    def status(self):
        if self.markers:
            return "resposta com aviso: " + ", ".join(self.markers)
        return "resposta" if self.addresses else "sem resposta"


@dataclass(frozen=True)
class TraceResult:
    host: str
    destination: str | None
    hops: tuple[Hop, ...]
    max_hops: int
    timeout: int
    wait_ms: int
    public_only: bool
    generated_at: str
    timed_out: bool = False
    returncode: int | None = 0
    message: str = ""

    @property
    def reached(self):
        return self.destination is not None and any(
            self.destination in hop.addresses for hop in self.hops)

    @property
    def visible_hops(self):
        if not self.public_only:
            return self.hops
        visible = []
        for hop in self.hops:
            addresses = tuple(value for value in hop.addresses if _public(value))
            if addresses:
                visible.append(replace(hop, addresses=addresses))
        return tuple(visible)


@dataclass(frozen=True)
class TraceProgress:
    elapsed: float
    kind: str
    hop: Hop | None = None


def validate_host(host):
    if (not isinstance(host, str) or not host or host != host.strip()
            or len(host) > 253 or any(ord(char) < 33 or ord(char) == 127 for char in host)
            or any(char in host for char in "/\\%[]@;|&$`<>\"'")):
        raise TraceError("Informe somente um host ou IP, sem URL, porta, caminho ou opções.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if ":" in host or re.fullmatch(r"[0-9.]+", host):
            raise TraceError("Endereço IP inválido.") from None
        try:
            hostname = host.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise TraceError("Nome de host inválido.") from None
        if len(hostname) > 253 or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in hostname.split(".")):
            raise TraceError("Nome de host inválido.")
        return hostname
    if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
        raise TraceError("Escolha um endereço de destino individual, sem multicast ou broadcast.")
    return str(address)


def _options(max_hops, timeout, wait_ms, public_only):
    for value, minimum, maximum, label in (
            (max_hops, 1, MAX_HOPS, "Hops"), (timeout, 1, MAX_TIMEOUT, "Timeout total"),
            (wait_ms, 100, 5000, "Espera por resposta em ms")):
        if type(value) is not int or not minimum <= value <= maximum:
            raise TraceError(f"{label}: informe um inteiro de {minimum} a {maximum}.")
    if type(public_only) is not bool:
        raise TraceError("O filtro de hops públicos deve ser verdadeiro ou falso.")


def _find_executable(system, ipv6=False):
    if system == "Windows":
        # Avoid selecting an unrelated tracert.exe from the working directory.
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tracert.exe"
        if executable.is_file():
            return str(executable)
        raise TraceError("tracert.exe não foi encontrado no diretório do Windows.")
    if system not in {"Linux", "Darwin"}:
        raise TraceError("Tracert/Pathtrace disponível para Windows, Linux e macOS.")
    name = "traceroute6" if system == "Darwin" and ipv6 else "traceroute"
    executable = shutil.which(name)
    if not executable:
        raise TraceError(f"{name} não está instalado ou não está no PATH. Instale o utilitário do sistema para usar esta opção.")
    return str(Path(executable).resolve())


def build_command(host, max_hops=30, wait_ms=1000, system=None):
    host = validate_host(host)
    _options(max_hops, 30, wait_ms, False)
    system = platform.system() if system is None else system
    try:
        ipv6 = ipaddress.ip_address(host).version == 6
    except ValueError:
        ipv6 = False  # Hostnames use IPv4; an IPv6 literal selects IPv6 explicitly.
    executable = _find_executable(system, ipv6)
    if system == "Windows":
        return [executable, "-d", "-h", str(max_hops), "-w", str(wait_ms),
                "-6" if ipv6 else "-4", host]
    # BSD/macOS traceroute wait times are integer seconds, so round up visibly.
    seconds = str((wait_ms + 999) // 1000) if system == "Darwin" else f"{wait_ms / 1000:g}"
    command = [executable, "-n", "-m", str(max_hops), "-w", seconds, "-q", "3"]
    if system == "Linux":
        command.append("-6" if ipv6 else "-4")
    return command + [host]


def _clean(value):
    return "".join(char for char in str(value) if char in "\n\t" or char.isprintable())


def _decode(value):
    if isinstance(value, str):
        return _clean(value)
    if not value:
        return ""
    encoding = locale.getpreferredencoding(False)
    if os.name == "nt":
        import ctypes
        encoding = "cp" + str(ctypes.windll.kernel32.GetOEMCP())
    return _clean(value.decode(encoding, errors="replace"))


def _addresses(line):
    found = []
    for token in re.split(r"[\s\[\](),]+", line):
        try:
            address = ipaddress.ip_address(token)
        except ValueError:
            continue
        value = str(address)
        if value not in found:
            found.append(value)
    return tuple(found)


def parse_hops(output, max_hops=MAX_HOPS):
    hops = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\d{1,3})\s+(.+)$", line)
        if not match or not 1 <= int(match[1]) <= max_hops:
            continue
        rest = match[2]
        addresses = _addresses(rest)
        timings = tuple((item[1].replace(" ", "").replace(",", ".") if item[1] else "*")
                        for item in re.finditer(r"(<\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*ms|\*", rest))
        if not addresses and not timings:
            continue
        markers = tuple(dict.fromkeys(re.findall(r"![A-Za-z0-9<>-]+", rest)))
        hops.append(Hop(int(match[1]), addresses, timings, markers))
    return tuple(hops)


def _destination(host, output):
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        # Read the destination from the native header; do not perform another DNS lookup.
        for line in output.splitlines():
            if re.match(r"^\s*\d+\s+", line):
                break
            addresses = _addresses(line)
            if addresses:
                return addresses[0]
    return None


def _public(value):
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast


def _run_live(command, arguments, timeout, max_hops, public_only, on_progress):
    """Drain a binary pipe in a reader thread; the main thread owns UI callbacks.

    Heartbeats remain visible even during DNS resolution or a silent hop. Raw
    native output is captured for the result, never sent directly to the UI.
    """
    options = {key: value for key, value in arguments.items() if key not in {"capture_output", "timeout"}}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, **options)
    chunks = queue.Queue(maxsize=32)
    stopped = threading.Event()
    output, pending = bytearray(), bytearray()
    started = time.monotonic()

    def enqueue(chunk):
        while not stopped.is_set():
            try:
                chunks.put(chunk, timeout=0.1)
                return
            except queue.Full:
                continue

    def read_output():
        try:
            while not stopped.is_set():
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                enqueue(chunk)
        except OSError:
            enqueue("read_error")
        finally:
            process.stdout.close()
            enqueue(None)

    def show_line(line):
        for hop in parse_hops(_decode(line), max_hops):
            if public_only:
                addresses = tuple(value for value in hop.addresses if _public(value))
                if not addresses:
                    continue
                hop = replace(hop, addresses=addresses)
            on_progress(TraceProgress(time.monotonic() - started, "hop", hop))

    def consume(chunk):
        if chunk == "read_error":
            raise TraceError("Não foi possível ler a saída do diagnóstico de rota.")
        if len(output) + len(chunk) > MAX_OUTPUT:
            raise TraceError("O utilitário retornou uma saída excessiva ou inesperada.")
        output.extend(chunk)
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, rest = pending.partition(b"\n")
            pending[:] = rest
            show_line(line)

    reader = threading.Thread(target=read_output, daemon=True, name="LittleBrother-tracert-output")
    reader.start()
    timed_out, eof = False, False
    next_tick = 1.0
    try:
        on_progress(TraceProgress(0.0, "started"))
        while not eof:
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                timed_out = True
                break
            if elapsed >= next_tick:
                on_progress(TraceProgress(elapsed, "waiting"))
                next_tick = elapsed + 1.0
            try:
                chunk = chunks.get(timeout=min(0.1, timeout - elapsed))
            except queue.Empty:
                continue
            if chunk is None:
                eof = True
            else:
                consume(chunk)
        if not timed_out:
            try:
                process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
        if timed_out:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            # Preserve bytes already received, including a final incomplete line.
            drain_until = time.monotonic() + 1.0
            while not eof and time.monotonic() < drain_until:
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    eof = True
                else:
                    consume(chunk)
        if pending:
            show_line(pending)
        on_progress(TraceProgress(time.monotonic() - started, "timeout" if timed_out else "finished"))
        if timed_out:
            raise subprocess.TimeoutExpired(command, timeout, output=bytes(output), stderr=b"")
        return subprocess.CompletedProcess(command, process.returncode, bytes(output), b"")
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=1)


def traceroute(host, max_hops=30, timeout=30, public_only=False, wait_ms=1000, *, on_progress=None):
    """Trace a single target with a bounded native subprocess; never use a shell."""
    host = validate_host(host)
    _options(max_hops, timeout, wait_ms, public_only)
    if on_progress is not None and not callable(on_progress):
        raise TraceError("O callback de progresso deve ser uma função.")
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        raise TraceError("Modo offline: Tracert/Pathtrace não envia sondagens de rede.")
    system = platform.system()
    if system == "Darwin":
        wait_ms = ((wait_ms + 999) // 1000) * 1000
    command = build_command(host, max_hops, wait_ms, system)
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "TEMP", "TMP"}}
    environment.update(LC_ALL="C", LANG="C")
    arguments = {"capture_output": True, "stdin": subprocess.DEVNULL, "timeout": timeout,
                 "shell": False, "env": environment}
    if os.name == "nt":
        arguments["creationflags"] = subprocess.CREATE_NO_WINDOW
    timed_out = False
    message = ""
    try:
        process = (subprocess.run(command, **arguments) if on_progress is None else
                   _run_live(command, arguments, timeout, max_hops, public_only, on_progress))
        output = _decode(process.stdout)
        stderr = _decode(process.stderr)
        returncode = process.returncode
    except subprocess.TimeoutExpired as exc:
        # Both runners kill and wait for the child before reporting a timeout.
        timed_out = True
        output = _decode(exc.stdout)
        stderr = _decode(exc.stderr)
        returncode = None
        message = "Timeout total atingido; os saltos capturados até a interrupção são parciais."
    except PermissionError:
        raise TraceError("O sistema negou a execução do diagnóstico. Verifique as permissões do utilitário.") from None
    except OSError:
        raise TraceError("Não foi possível executar o utilitário de rota do sistema.") from None
    if len(output) + len(stderr) > MAX_OUTPUT:
        raise TraceError("O utilitário retornou uma saída excessiva ou inesperada.")
    hops = parse_hops(output, max_hops)
    if returncode not in (0, None):
        message = "O utilitário terminou com erro (código %s)." % returncode
        if not hops:
            detail = " ".join((stderr or output).split())[:400]
            raise TraceError(message + (" " + detail if detail else " Verifique destino, permissões e conectividade."))
    elif not hops and not timed_out:
        raise TraceError("O utilitário não retornou saltos reconhecíveis. Verifique o destino e a instalação do traceroute.")
    return TraceResult(host, _destination(host, output), hops, max_hops, timeout, wait_ms,
                       public_only, generated, timed_out, returncode, message)


def render_text(result):
    lines = ["LittleBrother — Tracert / Pathtrace", f"Gerado em: {result.generated_at}",
             f"Host: {result.host}", f"Destino: {result.destination or 'não identificado'}",
             f"Máximo de hops: {result.max_hops} | Timeout total: {result.timeout}s | Espera por resposta: {result.wait_ms}ms",
             "Filtro: " + ("somente hops com IP público" if result.public_only else "todos os hops"),
             "IP do destino identificado nos saltos: " + ("sim" if result.reached else "não"),
             "Estado: " + ("parcial (timeout)" if result.timed_out else "erro do utilitário" if result.returncode else "processo encerrado")]
    if result.message:
        lines.append(result.message)
    lines.extend(["", "Hop | IP(s) | RTT em ms (* = sem resposta) | Estado"])
    for hop in result.visible_hops:
        lines.append(f"{hop.number} | {', '.join(hop.addresses) or '*'} | {' / '.join(hop.latencies_ms) or '*'} | {hop.status}")
    if not result.visible_hops:
        lines.append("Nenhum salto disponível para o filtro selecionado.")
    if result.public_only:
        lines.append("Saltos privados/reservados ou sem IP foram omitidos. O filtro também vale para as exportações.")
    lines.append("Asteriscos não comprovam falha de conectividade: roteadores e firewalls podem não responder às sondagens.")
    return "\n".join(lines) + "\n"


def _csv_cell(value):
    text = _clean(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def render_csv(result):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("gerado_em", "host", "destino", "max_hops", "timeout_total_s", "espera_ms",
                     "somente_publicos", "parcial_timeout", "codigo_saida", "destino_identificado",
                     "hop", "ips", "rtt_ms", "estado"))
    metadata = (result.generated_at, result.host, result.destination or "", result.max_hops, result.timeout,
                result.wait_ms, result.public_only, result.timed_out,
                "" if result.returncode is None else result.returncode, result.reached)
    for hop in result.visible_hops:
        writer.writerow(tuple(_csv_cell(value) for value in metadata +
                              (hop.number, "; ".join(hop.addresses), "; ".join(hop.latencies_ms), hop.status)))
    if not result.visible_hops:
        writer.writerow(tuple(_csv_cell(value) for value in metadata + ("", "", "", "sem saltos para o filtro")))
    return buffer.getvalue()


def export_trace(result, format="txt", directory=None):
    if format not in {"txt", "csv"}:
        raise TraceError("Formato de exportação inválido: escolha txt ou csv.")
    root = Path(directory).expanduser().resolve() if directory is not None else settings.data_directory()
    folder = root / "traces"
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise TraceError("A pasta de exportação não pode apontar para fora do diretório escolhido.")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = "trace_" + uuid.uuid4().hex + "." + format
    destination = folder / filename
    data = render_csv(result) if format == "csv" else render_text(result)
    # A generated basename plus exclusive creation prevents path traversal/overwrites.
    created = False
    try:
        with destination.open("x", encoding="utf-8-sig" if format == "csv" else "utf-8", newline="") as output:
            created = True
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        if created:
            destination.unlink(missing_ok=True)
        raise TraceError("Não foi possível gravar a exportação na pasta de relatórios.") from None
    return destination


def _input_integer(label, default):
    text = input(f" {label} [{default}]: ").strip()
    try:
        return default if not text else int(text)
    except ValueError:
        raise TraceError("Informe um número inteiro para " + label.lower() + ".") from None


def pathtrace_lookup():
    if os.environ.get("LITTLEBROTHER_OFFLINE", "").lower() in {"1", "true", "yes"}:
        print("[!] Modo offline: Tracert/Pathtrace não envia sondagens de rede.")
        return
    host = input(" Host ou IP de destino (sem http://): ").strip()
    max_hops = _input_integer("Máximo de hops (1–64)", 30)
    timeout = _input_integer("Timeout total em segundos (1–180)", 30)
    wait_ms = _input_integer("Espera por resposta em ms (100–5000)", 1000)
    answer = input(" Mostrar apenas hops públicos? [s/N]: ").strip().casefold()
    if answer not in {"", "s", "sim", "y", "yes", "n", "não", "nao", "no"}:
        raise TraceError("Responda s ou n para o filtro de hops públicos.")
    public_only = answer in {"s", "sim", "y", "yes"}
    def log_progress(event):
        prefix = f"[{event.elapsed:5.1f}s]"
        if event.kind == "hop":
            hop = event.hop
            text = (f"Hop {hop.number:02d} | {', '.join(hop.addresses) or '*'} | "
                    f"RTT: {' / '.join(hop.latencies_ms) or '*'} ms | {hop.status}")
        elif event.kind == "started":
            text = f"Diagnóstico iniciado. Limite total: {timeout}s. Ctrl+C para interromper."
        elif event.kind == "waiting":
            text = "Diagnóstico em andamento; aguardando novas respostas do utilitário..."
        elif event.kind == "timeout":
            text = "Timeout total atingido; preparando os resultados parciais."
        else:
            text = "Processo encerrado; preparando o resultado."
        print(f"{prefix} {text}", flush=True)

    print("[I] Diagnóstico nativo em andamento; o timeout limita a execução do processo.", flush=True)
    result = traceroute(host, max_hops=max_hops, timeout=timeout, public_only=public_only,
                        wait_ms=wait_ms, on_progress=log_progress)
    print(render_text(result))
    while True:
        choice = input(" Exportar: [1] CSV  [2] Texto  [Enter/b] Voltar: ").strip().lower()
        if choice in {"", "b", "voltar"}:
            return result
        if choice in {"e", "exit", "sair"}:
            raise EOFError
        if choice not in {"1", "2"}:
            print("[!] Escolha 1, 2 ou Enter para voltar.")
            continue
        path = export_trace(result, "csv" if choice == "1" else "txt")
        print("[+] Exportado: " + str(path))
