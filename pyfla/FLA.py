"""
CS5 .FLA parser

Usage example:

Merge Flash CS5 .FLA files, joining library objects

>>> fla = FLA.fromfile('Element1.fla') + FLA.fromfile('Element2.fla')
>>> fla.save('Merged.fla')
"""

import glob
import re
import sys, os
import shutil
import tempfile
from hashlib import md5
from odict import OrderedDict
from xml.etree.cElementTree import fromstring

from fileoperations import fzip, funzip, fixencoding

# Get current script directory and append template path
TPL_PATH = os.path.dirname(os.path.realpath(__file__)) + '/templates'


class InvalidFLAFile(Exception):
    """
    This exception is raised when we cannot parse given FLA file
    """


def _unicode(val):
    # Decode string as needed checking if this is already decoded
    return unicode(val, 'utf-8') if isinstance(val, str) else val

def _fix_insensitive_path(path):
    # Some files could have an incorrect path information on case-insensitive
    # FS. This could cause lost of some symbols. This fix the case.
    bpath = os.path.basename(path)
    ipath = bpath.lower()
    for f in glob.glob("%s/../*" % path):
        base = os.path.basename(f)
        if ipath == base.lower() and base != bpath:
            shutil.move(f, path + 'temp')
            shutil.move(path + 'temp', path)
            return

def _tag_from_dict(tag, attrs, terminate=True):
    attrs = ''.join('%s="%s" ' % (k, v.replace('&', '&amp;')) \
                        for k, v in attrs.iteritems())
    return u'<%s %s%s>' % (tag, _unicode(attrs), '/' if terminate else '')


class FLA(object):
    """
    FLA Object could be instanced using specific configuration or
    using static method fromfile() which will decompress given FLA
    file and parse needed configuration.
    """

    def __init__(self, **kwargs):
        self.symbols = {}
        self.folders = OrderedDict()
        self.directory = kwargs.get('directory') or tempfile.mkdtemp()

        # Load default configuration
        default_config = {
            'width': 760,
            'height': 600,
            'name': 'Empty',
            'mimetype': 'application/vnd.adobe.xfl',
            'xconf': open('%s/PublishSettings.xml' % TPL_PATH).read(),
            'xdom': open('%s/DOMDocument.xml' % TPL_PATH).read()
        }

        # Update with function arguments
        default_config.update(kwargs)

        # Save kwargs as attributes
        for k, v in default_config.iteritems():
            setattr(self, k, v)

    def __del__(self):
        # Remove unused temporary folder
        shutil.rmtree(self.directory)

    @classmethod
    def fromfile(klass, filepath):
        """
        Creates a new FLA object parsing given file (full path please)
        """
        _dir = tempfile.mkdtemp()

        funzip(filepath, _dir)
        
        if not os.path.isfile('%s/DOMDocument.xml' % _dir):
            raise InvalidFLAFile("%s is not a valid Flash CS5 file" % filepath)

        # Parse XML file
        xml = open('%s/DOMDocument.xml' % _dir).read()
        dom = fromstring(xml)
        xmlns = dom.tag.split('}')[0][1:] if dom.tag.startswith('{') else ''

        # Parse all library folders
        fla = FLA(name=os.path.basename(filepath).split('.')[0], 
                  directory=_dir)

        domfolders = dom.find("{%s}folders" % xmlns)
        if domfolders is not None:
            for folder in domfolders.getchildren():
                path = folder.attrib['name']
                uid = md5(path.encode('utf-8')).hexdigest()
                _fix_insensitive_path(os.path.join(_dir, 'LIBRARY', path))

                fla.folders[path] = {
                    'name': path,
                    'itemID': "0000%s-0000%s" % (uid[:4], uid[4:8])
                }

        # Parse all library symbols
        domsymbols = dom.find("{%s}symbols" % xmlns)
        if domsymbols is not None:
            childs = domsymbols.getchildren()
            for symbol in childs:
                name = symbol.attrib['href'][:-4]
                try:
                    fla.symbols[name] = Symbol(symbol.attrib, fla.symbols,
                                               fla.directory)
                except IOError:
                    # In some scenarios, there is referenced symbols that 
                    # doesn't exists on directory.
                    continue

        return fla

    def __str__(self):
        # Visualization candy
        return "<FLA '%s' symbols=%d folders=%d>" % \
                (self.name, len(self.symbols), len(self.folders))
    
    def _replace_template(self, tpl, values):
        # Replace into given template (string) some dinamic values 
        for k, v in values.iteritems():
            if isinstance(v, unicode):
                v = v.encode('utf-8')

            if isinstance(v, str):
                tpl = tpl.replace("{{ %s }}" % k, v)

        return tpl

    def save(self, filepath):
        """
        Read our not_saved record, craft xml, zip and save into given filepath
        """
        self.name = os.path.basename(filepath).split('.')[0]

        xmlfolders = u'\n'.join(_tag_from_dict('DOMFolderItem', f)\
                for f in self.folders.itervalues())
        
        # Sort Items, to avoid some Flash Crashes (!!!)
        symbols = self.symbols.values()
        symbols.sort(key=lambda x: x.attrs['href'])
        xmlsymbols = u'\n'.join(s.to_xml() for s in symbols)

        xdom = self._replace_template(self.xdom, 
                {'folders_xml': xmlfolders, 'symbols_xml': xmlsymbols})
        xconf = self._replace_template(self.xconf, 
                dict((k, getattr(self, k)) for k in dir(self) if k[0] != '_'))

        open('%s/mimetype' % self.directory, 'w').write(self.mimetype)
        open('%s/DOMDocument.xml' % self.directory, 'w').write(xdom)
        open('%s/PublishSettings.xml' % self.directory, 'w').write(xconf)
        open('%s/%s.xfl' % (self.directory, self.name), 'w').write('PROXY-CS5')

        # Make FLA file (Just a regular zip file)
        fzip(filepath, self.directory)

    @classmethod
    def from_symbols(klass, symbols, fladirectory=None, flainstance=None):
        paths = lambda n: [] \
            if n == os.path.dirname(n) else paths(os.path.dirname(n)) + [n]

        newfla = flainstance or FLA(name='dynamic')
        newfla.symbols = symbols
        if fladirectory:
            newfla.directory = fladirectory

        for ohref, symbol in symbols.items():
            href = os.path.dirname(symbol.attrs['href'])

            # Fill up folders automatically, based on symbols
            for path in paths(href):
                uid = md5(path.encode('utf-8')).hexdigest()
                newfla.folders[path] = {
                    'name': path,
                    'itemID': "0000%s-0000%s" % (uid[:4], uid[4:8])
                }

            dest_file = "%s/LIBRARY/%s.xml" % (newfla.directory, ohref)
            dest_dir = os.path.dirname(dest_file)

            # Create directory if it does not exists
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir)

            if os.path.dirname(symbol.xml) != dest_dir:
                shutil.copy(symbol.xml, dest_dir)

            newfla.symbols[ohref].xml = dest_file

        return newfla

    def __add__(self, other):
        """
        Implement + operator to merge FLA files. This will be return a new copy
        of the object.
        """
        if not isinstance(other, FLA):
            raise TypeError("You cannot add other than FLA object")

        symbols = dict(self.symbols, **other.symbols)
        return FLA.from_symbols(symbols)

    def append(self, other):
        """
        Append symbols from other FLA files. This will not return a new copy
        of the object.
        """
        if not isinstance(other, FLA):
            raise TypeError("You cannot add other than FLA object")

        symbols = dict(self.symbols, **other.symbols)
        return FLA.from_symbols(symbols, self.directory, self)


ENTITIES_FIX = (':', '<', '>')
class Symbol(object):
    """
    Symbol representation (This is created using actual symbol XML file)
    and reference tag fro DOMDocument.xml
    """

    def __init__(self, tag, symbols, directory):
        self._symbols = symbols
        self._depcache = None
        self._instances = None
        self._linkage = None

        self.attrs = tag

        # Get xml filename and remove extension
        self.name = _unicode(os.path.basename(tag['href'])[:-4])
        self.xml = "%s/LIBRARY/%s" % (directory, tag['href'])

        # Fix filesystem encoding
        fixencoding(self.xml)

        self.dom = fromstring(open(self.xml).read())
        self.dom.attrib['xmlns'] = self.dom.tag.split('}')[0][1:]

    def to_xml(self):
        return _tag_from_dict("Include", self.attrs)

    def _get_linkage(self):
        if self._linkage: return self._linkage

        if 'linkageClassName' not in self.dom.attrib:
            self._linkage = None
        else:
            self._linkage = self.dom.attrib['linkageClassName']

        return self._linkage

    def __str__(self):
        # Visualization candy
        return "<Symbol %s>" % self.name

    def _set_linkage(self, name):
        # Set symbol linkage name (Class name used in actionscript)
        self.dom.attrib['linkageClassName'] = name
        self.dom.attrib['linkageExportForAS'] = "true"

        # Change XML file
        tag = _tag_from_dict('DOMSymbolItem', self.dom.attrib, 
                             terminate=False)
        newxml = re.sub(u'<DOMSymbolItem.*?>', tag, 
                        open(self.xml).read().decode('utf-8'))

        # Save xml
        open(self.xml, 'w').write(newxml.encode('utf-8'))

        # This flag is used to make the linkage loaded at Flash IDE boot time
        if 'loadImmediate' in self.attrs:
            del self.attrs['loadImmediate']

        self._linkage = name

    def _dependencies(self):
        if self._depcache == None:
            self._depcache = set()
            self._instances = []
            ns = self.dom.attrib['xmlns']

            # Iterate through dependencies and set up needed properties
            for ttimeline in self.dom.getiterator("{%s}DOMTimeline" % ns):
                for tlayer in ttimeline.getiterator("{%s}DOMLayer" % ns):
                    for tframe in tlayer.getiterator("{%s}DOMFrame" % ns):
                        tagname = "{%s}DOMSymbolInstance" % ns
                        for tsymb in tframe.getiterator(tagname):
                            # Fix "<" and ">" characters from xml
                            name = tsymb.attrib['libraryItemName']

                            for char in ENTITIES_FIX:
                                name = name.replace(char, "&#%d" % ord(char))

                            # Get Symbol instance from FLA Object
                            symbol = self._symbols[name]
                            instance = SymbolInstance(
                                symbol=symbol, name=tsymb.attrib["name"],
                                frame=tframe.attrib["index"],
                                layer=tlayer.attrib["name"],
                                timeline=ttimeline.attrib["name"]
                            )

                            self._instances.append(instance)
                            self._depcache.add(symbol)
                            self._depcache = self._depcache.union(
                                    symbol.dependencies)
        
        return self._depcache

    def _instances(self):
        if self._instances == None:
            self._dependencies()

        return self._instances

    linkage = property(_get_linkage, _set_linkage)
    dependencies = property(_dependencies)
    instances = property(_instances)


class SymbolInstance(object):
    """
    This object represents an instance found in a timeline for a given symbol
    """

    def __init__(self, symbol, name, frame, layer, timeline):
        self.symbol = symbol
        self.name = _unicode(name)
        self.frame = int(frame) + 1
        self.layer = _unicode(layer)
        self.timeline = _unicode(timeline)
