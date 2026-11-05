"""Read image metadata locally without uploading a file."""
from pathlib import Path

import exifread


def read_exif(filename):
    path = Path(filename).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".tif", ".tiff"}:
        raise ValueError("Escolha um arquivo JPEG ou TIFF local.")
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("A imagem excede o limite de 32 MB.")
    with path.open("rb") as image:
        tags = exifread.process_file(image, details=False, strict=False)
    return {key: str(value) for key, value in sorted(tags.items())
            if key not in {"JPEGThumbnail", "TIFFThumbnail"}}


def exifRead():
    tags = read_exif(input("Caminho da imagem local: ").strip().strip('"'))
    if not tags:
        print("Nenhuma tag EXIF encontrada. O arquivo permaneceu local.")
    for key, value in tags.items():
        value = "".join(c for c in value if c.isprintable())
        print(f"{key}: {value}")
