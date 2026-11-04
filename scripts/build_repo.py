#!/usr/bin/env python3
"""Build this flat APT repository with Python 3 (no dpkg tools required)."""
import bz2
import gzip
import hashlib
import io
import os
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def ar_members(blob):
    """Read standard Debian ar archives, including GNU trailing-slash names."""
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("Not an ar archive")
    offset = 8
    while offset < len(blob):
        header = blob[offset:offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError("Invalid ar header")
        size = int(header[48:58])
        if size < 0 or offset + 60 + size > len(blob):
            raise ValueError("Invalid ar member size")
        name = header[:16].decode("ascii").strip()
        data = blob[offset + 60:offset + 60 + size]
        if name.startswith("#1/"):
            length = int(name[3:])
            name, data = data[:length].rstrip(b"\0").decode(), data[length:]
        yield name.rstrip("/"), data
        offset += 60 + size + size % 2


def parse_fields(text):
    fields = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and key:
            fields[key] += "\n" + line
        else:
            key, sep, value = line.partition(":")
            if not sep or not key or key in fields:
                raise ValueError(f"Invalid or duplicate control field: {line!r}")
            fields[key] = value.strip()
    return fields


def render(fields):
    return "".join(f"{key}:{'' if value.startswith(chr(10)) else ' '}{value}\n"
                   for key, value in fields.items() if value)


def package_fields(path):
    blob = path.read_bytes()
    members = dict(ar_members(blob))
    if members.get("debian-binary", b"").strip() != b"2.0":
        raise ValueError(f"Unsupported deb version: {path.name}")
    controls = [data for name, data in members.items()
                if name == "control.tar" or name.startswith("control.tar.")]
    if len(controls) != 1:
        raise ValueError(f"Expected one control archive: {path.name}")
    # Read metadata only; never extract files or execute maintainer scripts.
    with tarfile.open(fileobj=io.BytesIO(controls[0]), mode="r:*") as archive:
        matches = [m for m in archive.getmembers()
                   if m.name.removeprefix("./") == "control" and m.isfile()]
        if len(matches) != 1:
            raise ValueError(f"Expected one control file: {path.name}")
        fields = parse_fields(archive.extractfile(matches[0]).read().decode("utf-8"))
    for key in ("Package", "Version", "Architecture"):
        if not fields.get(key):
            raise ValueError(f"Missing {key}: {path.name}")
    fields.update({
        "Filename": "./" + path.name,
        "Size": str(len(blob)),
        "MD5sum": hashlib.md5(blob).hexdigest(),
        "SHA1": hashlib.sha1(blob).hexdigest(),
        "SHA256": hashlib.sha256(blob).hexdigest(),
    })
    return fields


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".repo-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    packages = [package_fields(p) for p in sorted(ROOT.glob("*.deb"))]
    if not packages:
        raise ValueError("No deb files found; refusing to publish an empty index")
    identities = [(p["Package"], p["Version"], p["Architecture"]) for p in packages]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate package/version/architecture")
    content = ("\n".join(render(p) for p in packages) + "\n").encode("utf-8")
    outputs = {
        "Packages": content,
        "Packages.gz": gzip.compress(content, mtime=0),
        "Packages.bz2": bz2.compress(content),
    }
    release = parse_fields((ROOT / "Release").read_text())
    for key in ("MD5Sum", "SHA1", "SHA256", "SHA512"):
        release.pop(key, None)
    release["Architectures"] = " ".join(sorted({p["Architecture"] for p in packages}))
    for field, algorithm in (("MD5Sum", "md5"), ("SHA256", "sha256")):
        release[field] = "\n" + "\n".join(
            f" {hashlib.new(algorithm, data).hexdigest()} {len(data)} {name}"
            for name, data in outputs.items()
        )
    outputs["Release"] = render(release).encode("utf-8")
    # Validate everything before replacing any output; Release is replaced last.
    for name, data in outputs.items():
        atomic_write(ROOT / name, data)
    print(f"Built {len(packages)} packages; architectures: {release['Architectures']}")
    for p in packages:
        print(f"  {p['Package']} {p['Version']} ({p['Architecture']})")


if __name__ == "__main__":
    main()
