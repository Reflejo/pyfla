import os, sys
import shutil
import subprocess
import zipfile

BACKPORT_UNZIP = '/opt/local/bin/unzip -o -d %s "%s"'
BACKPORT_ZIP = 'cd %s && /usr/bin/zip -q -r "%s" *'

def fzip(filename, path):
    if not filename.startswith('/'):
        filename = '%s/%s' % (os.getcwd(), filename)

    run = BACKPORT_ZIP % (path, filename)
    proc = subprocess.Popen(run, shell=True, stderr=subprocess.PIPE, 
                                stdout=subprocess.PIPE)
    proc.wait()

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

    if sys.platform == 'linux2':
        value = unicodedata.normalize('NFKD', filename)
        return value.encode('utf-8')

    if sys.platform == 'darwin':
        return filename.encode('utf-8')
