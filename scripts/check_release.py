"""Validate the exact wheel/source files selected for publication."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import tarfile
import tomllib
import zipfile


def canonical(name):return re.sub('[-_.]+','-',name).lower()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory');parser.add_argument('--tag',required=True)
    parser.add_argument('--output',default='release-artifacts.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    project=tomllib.loads((root/'pyproject.toml').read_text())['project']
    if args.tag!='v'+project['version']:raise ValueError('Release tag does not match package metadata')
    folder=Path(args.directory);wheels=sorted(folder.glob('*.whl'));sources=sorted(folder.glob('*.tar.gz'))
    if len(wheels)!=1 or len(sources)!=1 or len([p for p in folder.iterdir() if p.name!='.gitignore'])!=2:
        raise ValueError('Publish exactly one wheel and one source distribution')
    records=[]
    for artifact in wheels+sources:
        if artifact.suffix=='.whl':
            with zipfile.ZipFile(artifact) as archive:
                names=archive.namelist();paths=[n for n in names if n.endswith('.dist-info/METADATA')]
                if len(paths)!=1:raise ValueError('Wheel metadata is ambiguous')
                raw=archive.read(paths[0])
        else:
            with tarfile.open(artifact,'r:gz') as archive:
                names=archive.getnames();paths=[n for n in names if n.endswith('/PKG-INFO') and n.count('/')==1]
                if len(paths)!=1:raise ValueError('Source metadata is ambiguous')
                stream=archive.extractfile(paths[0])
                if stream is None:raise ValueError('Source metadata is absent')
                with stream:raw=stream.read()
        metadata=BytesParser().parsebytes(raw)
        if canonical(metadata['Name'])!=canonical(project['name']) or metadata['Version']!=project['version']:
            raise ValueError('Artifact identity does not match the selected release')
        if metadata['Requires-Python']!=project['requires-python']:raise ValueError('Python support metadata differs')
        if not metadata.get_payload().strip():raise ValueError('The published long description is empty')
        if any('@' in requirement for requirement in metadata.get_all('Requires-Dist',[])):
            raise ValueError('Published dependency metadata must use package-index requirements, including extras')
        if not metadata.get('License-Expression') and not metadata.get('License'):raise ValueError('Declare the existing license in metadata')
        if not any(Path(n).name.lower().startswith(('license','copying')) for n in names):raise ValueError('Artifact license text is absent')
        for name in names:
            path=Path(name)
            if path.name=='.env' or '.venv' in path.parts or path.suffix in ('.tft','.safetensors','.pt','.sqlite3'):
                raise ValueError('Private execution artifacts are outside the package release')
        records.append({'filename':artifact.name,'bytes':artifact.stat().st_size,
                        'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()})
    receipt={'distribution':project['name'],'version':project['version'],'tag':args.tag,'artifacts':records}
    Path(args.output).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
