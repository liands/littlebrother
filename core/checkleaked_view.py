"""Terminal-only layout for CheckLeaked metadata; no network or persistence."""
from datetime import date, datetime
import shutil
import textwrap

from terminaltables import AsciiTable

from core.dns_lookup import _display


def _date(value):
    raw = str(value or "").strip()
    if not raw or raw.casefold() in {"não informado", "unknown", "n/a"}:
        return "N/D"
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return _display(raw)
    return parsed.strftime("%d/%m/%Y")


def render_checkleaked(data, *, width=None):
    columns = width if width is not None else shutil.get_terminal_size(fallback=(100, 24)).columns
    columns = max(24, min(columns, 110))
    available = columns - 2

    def wrap(value, indent="  "):
        continuation = " " * len(indent) if indent.strip() == "-" else indent
        return textwrap.fill(str(value), width=columns, initial_indent=indent, subsequent_indent=continuation,
                             break_long_words=True, break_on_hyphens=False)

    sources = sorted(data["sources"], key=lambda item: (_display(item["name"]).casefold(), str(item["date"])))
    lines = [wrap("RESUMO DA EXPOSIÇÃO"),
             wrap(f"Registros informados : {data['count']}"),
             wrap(f"Fontes/datas listadas: {len(sources)}")]
    if "rows_analyzed" in data and "rows_received" in data:
        lines.append(wrap(f"Linhas analisadas    : {data['rows_analyzed']} de {data['rows_received']} recebidas"))
    lines.append("")
    if sources:
        if columns >= 64:
            number_width = max(1, len(str(len(sources))))
            count_width = max(len("Registros"), *(len(str(item["records"])) for item in sources))
            name_width = available - (number_width + 10 + count_width + 13)
            rows = [["#", "Fonte / vazamento", "Data", "Registros"]]
            for index, source in enumerate(sources, 1):
                rows.append([str(index), textwrap.fill(_display(source["name"]), width=name_width,
                             break_long_words=True, break_on_hyphens=False),
                             textwrap.fill(_date(source["date"]), width=10), str(source["records"])])
            table = AsciiTable(rows, title="Fontes identificadas")
            table.justify_columns[0] = "right"
            table.justify_columns[3] = "right"
            lines.extend("  " + line for line in table.table.splitlines())
        else:
            lines.append(wrap("FONTES IDENTIFICADAS"))
            for index, source in enumerate(sources, 1):
                lines.extend([wrap(f"{index:02d}. {_display(source['name'])}"),
                              wrap(f"Data: {_date(source['date'])}"),
                              wrap(f"Registros analisados: {source['records']}"), ""])
        lines.append(wrap("N/D = data não informada. Fontes em ordem alfabética, separadas por data."))
    elif data["count"]:
        lines.append(wrap("O serviço informou exposição, mas não forneceu metadados das fontes nesta resposta."))
    else:
        lines.append(wrap("Nenhum registro foi retornado nesta consulta. Isso não comprova ausência de exposição."))
    if data["fields"]:
        lines.extend(["", wrap("TIPOS DE DADOS EXPOSTOS")])
        for field in data["fields"]:
            label = _display(field)
            label = label[:1].upper() + label[1:]
            lines.append(wrap(label, indent="    - "))
    lines.append("")
    if data["partial"]:
        lines.append(wrap("Resultado parcial: há registros não detalhados. Nenhuma busca adicional foi feita."))
    if data["count"]:
        lines.append(wrap("Uma linha pode citar várias fontes; as contagens não são somadas como vazamentos únicos."))
    lines.append(wrap("Senhas, hashes e valores de credenciais não são exibidos nem gravados."))
    return "\n".join(lines)
