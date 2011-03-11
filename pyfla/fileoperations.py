import os, sys
import shutil
import subprocess
import unicodedata
import zipfile

BACKPORT_UNZIP = '/opt/local/bin/unzip -o -d %s "%s"'
BACKPORT_ZIP = 'cd %s && /opt/local/bin/zip -q -r "%s" *'

def fzip(filename, path):
    # Compress FLA file using zipfile python library
    os.chdir(path)

    tree = list(os.walk('.'))
    myzip = zipfile.ZipFile(filename, 'w')
    for parent, dirs, files in tree:
        for file in files:
            if isinstance(file, str):
                file = file.decode('utf-8')

            file = unicodedata.normalize("NFC", file).encode('utf-8')
            myzip.write('%s/%s' % (parent, file))

    myzip.close()

def funzip(filename, path):
    # Extract FLA file inside a temporary directory trying default 
    # python zip library, if doesn't work try unzip
    try:
        zf = zipfile.ZipFile(filename)
        zf.extractall(path=path)
    except (zipfile.BadZipfile, IOError):
        shutil.rmtree(path)
        run = BACKPORT_UNZIP % (path, filename)
        proc = subprocess.Popen(run, shell=True, stderr=subprocess.PIPE, 
                                stdout=subprocess.PIPE)
        out = proc.stdout.read()
        proc.wait()

def fsencode(filename):
    """
    Encode filename according to platform
    """
    if isinstance(filename, str):
        filename = filename.decode('utf-8')

    value = unicodedata.normalize('NFKD', filename)
    return value.encode('utf-8')
