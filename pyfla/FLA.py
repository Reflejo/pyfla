"""
Merge Flash CS5 .FLA files, joining library objects

Usage:

>>> fla = FLA.fromfile('Element1.fla') + FLA.fromfile('Element2.fla')
>>> fla.save('Merged.fla')
"""

import re
import sys, os
import shutil
import tempfile
from hashlib import md5
from odict import OrderedDict
from xml.etree.cElementTree import fromstring

from fileoperations import fzip, funzip, fsencode

# Get current script directory and append template path
TPL_PATH = os.path.dirname(os.path.realpath(__file__)) + '/templates'


class InvalidFLAFile(Exception):
    """
    This exception is raised when we cannot parse given FLA file
    """

def _tag_from_dict(tag, attrs, terminate=True):
    attrs = u''.join(u'%s="%s" ' % (k, v.replace('&', '&amp;')) \
                        for k, v in attrs.iteritems())
    return u'<%s %s%s>' % (tag, attrs, '/' if terminate else '')


class FLA(object):
    """
    FLA Object could be instanced using specific configuration or
    using static method fromfile() which will decompress given FLA
    file and parse needed configuration.
    """

    def __init__(self, **kwargs):
        self.symbols = {}
        self.folders = OrderedDict()
        self.directory = tempfile.mkdtemp()

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
                fla.symbols[name] = Symbol(symbol.attrib, fla)

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
        xmlsymbols = u'\n'.join(s.to_xml() for s in self.symbols.itervalues())

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
    def from_symbols(klass, symbols, fladirectory=None):
        paths = lambda n: [] \
            if n == os.path.dirname(n) else paths(os.path.dirname(n)) + [n]

        newfla = FLA(name='dynamic')
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
            dest_dir = fsencode(os.path.dirname(dest_file))

            # Create directory if it does not exists
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir)

            if os.path.dirname(fsencode(symbol.xml)) != dest_dir:
                shutil.copy(fsencode(symbol.xml), dest_dir)

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
        return FLA.from_symbols(symbols, self.directory)


ENTITIES_FIX = (':', '<', '>')
class Symbol(object):
    """
    Symbol representation (This is created using actual symbol XML file)
    and reference tag fro DOMDocument.xml
    """

    def __init__(self, tag, FLA):
        self._fla = FLA
        self.timeline = self.layer = self.frame = None
        self._depcache = None
        self._linkage = None

        self.attrs = tag

        # Get xml filename and remove extension
        self.name = os.path.basename(tag['href'])[:-4]
        if isinstance(self.name, str):
            self.name = unicode(self.name, 'utf-8')

        self.xml = "%s/LIBRARY/%s" % (FLA.directory, tag['href'])

        self.dom = fromstring(open(fsencode(self.xml)).read())
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
                        open(fsencode(self.xml)).read().decode('utf-8'))

        # Save xml
        open(fsencode(self.xml), 'w').write(newxml.encode('utf-8'))

        # This flag is used to make the linkage loaded at Flash IDE boot time
        if 'loadImmediate' in self.attrs:
            del self.attrs['loadImmediate']

        self._linkage = name

    def _dependencies(self):
        if self._depcache == None:
            self._depcache = set()
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
                            symbol = self._fla.symbols[name]
                            symbol.frame = tframe.attrib
                            symbol.layer = tlayer.attrib
                            symbol.timeline = ttimeline.attrib

                            self._depcache.add(symbol)
                            self._depcache = self._depcache.union(
                                    symbol.dependencies)
        
        return self._depcache

    linkage = property(_get_linkage, _set_linkage)
    dependencies = property(_dependencies)
