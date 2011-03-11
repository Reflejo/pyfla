import os, sys
import shutil
import subprocess
import unicodedata
import zipfile

BACKPORT_UNZIP = '/opt/local/bin/unzip -o -d %s "%s"'
BACKPORT_ZIP = 'cd %s && /opt/local/bin/zip -q -r "%s" *'

def normalize(value):
    if isinstance(value, str):
        value = value.decode('utf-8')

    value = unicodedata.normalize("NFC", value).encode('utf-8')
    return value

def fzip(filename, path):
    # Compress FLA file using zipfile python library
    os.chdir(path)

    tree = list(os.walk('.'))
    myzip = zipfile.ZipFile(filename, 'w')
    for parent, dirs, files in tree:
        for file in files:
            myzip.write('%s/%s' % (parent, normalize(file)))

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

def fixencoding(path):
    """
    Fix filenames and directories with a wrong encoding. This behavoir is there
    because unzip is setting wrong the encoding.
    """
    upath = unicode(path, 'utf-8') if isinstance(path, str) else path
    path = upath.encode('utf-8')

    encoded = unicodedata.normalize('NFKD', upath).encode('utf-8')
    basedir = os.path.dirname(path)
    # Create fixed directory names as needed
    if not os.path.isdir(basedir):
        os.makedirs(basedir)

    # Create fixed file names as needed
    if not os.path.isfile(encoded):
        encoded = "%s/%s" % (os.path.dirname(encoded), os.path.basename(path))

    if encoded != path and not os.path.isfile(path):
        shutil.copy(encoded, path)
