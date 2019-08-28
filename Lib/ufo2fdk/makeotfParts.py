from __future__ import absolute_import
import codecs
import os
import shutil
import re
from ufo2fdk.fontInfoData import getAttrWithFallback, intListToNum, normalizeStringForPostscript
from ufo2fdk.outlineOTF import OutlineOTFCompiler
from ufo2fdk.featureTableWriter import FeatureTableWriter, winStr, macStr
from ufo2fdk.kernFeatureWriter import KernFeatureWriter
import unicodedata


def toBytes(s, encoding="utf-8"):
    return s.encode(encoding)


class MakeOTFPartsCompiler(object):

    """
    This object will create the "parts" needed by the FDK.
    The only external method is :meth:`ufo2fdk.tools.makeotfParts.compile`.
    There is one attribute, :attr:`ufo2fdk.tools.makeotfParts.path`
    that may be referenced externally. That is a dictionary of
    paths to the various parts.

    When creating this object, you must provide a *font*
    object and a *path* indicating where the parts should
    be saved. Optionally, you can provide a *glyphOrder*
    list of glyph names indicating the order of the glyphs
    in the font. You may also provide an *outlineCompilerClass*
    argument that will serve as the outline source compiler.
    The class passed for this argument must be a subclass of
    :class:`ufo2fdk.tools.outlineOTF.OutlineOTFCompiler`.
    """

    def __init__(self, font, path, features=None, glyphOrder=None, glyphDesignNameToFinalNameMap=None, outlineCompilerClass=OutlineOTFCompiler):
        self.font = font
        self.path = path
        self.log = []
        self.outlineCompilerClass = outlineCompilerClass
        # store the path to an eventual custom feature file
        self.features = features
        # store the glyph order
        if glyphOrder is None:
            glyphOrder = sorted(font.keys())
        self.glyphOrder = glyphOrder
        # set up the production names
        self.glyphDesignNameToFinalNameMap = self.makeGlyphDesignNameToFinalNameMap(glyphDesignNameToFinalNameMap)
        # make the paths for all files
        self.paths = dict(
            outlineSource=os.path.join(path, "font.otf"),
            menuName=os.path.join(path, "menuname"),
            glyphOrder=os.path.join(path, "glyphOrder"),
            fontInfo=os.path.join(path, "fontinfo"),
            features=os.path.join(path, "features")
        )

    def makeGlyphDesignNameToFinalNameMap(self, providedMap):
        """
        Make a map of {glyphName : makeotfLegalGlyphName}
        for all gyphs in the glyph order..
        """
        finalMap = {}
        if providedMap is not None:
            finalMap.update(providedMap)
        # gather glyphs that need a final name
        needFinalName = [glyphName for glyphName in self.glyphOrder if glyphName not in finalMap]
        # store names that don't need to be changed
        for glyphName in needFinalName:
            if isLegalGlyphName(glyphName):
                finalMap[glyphName] = glyphName
        # make names for the rest
        for glyphName in needFinalName:
            if glyphName in finalMap:
                continue
            uniValue = None
            if glyphName in self.font:
                uniValue = self.font[glyphName].unicode
            finalMap[glyphName] = normalizeGlyphName(glyphName, uniValue, finalMap.values())
        # done
        return finalMap

    def compile(self):
        """
        Compile the parts.
        """
        # set up the parts directory removing
        # an existing directory if necessary.
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
        os.mkdir(self.path)
        # build the parts
        self.setupFile_outlineSource(self.paths["outlineSource"])
        self.setupFile_menuName(self.paths["menuName"])
        self.setupFile_glyphOrder(self.paths["glyphOrder"])
        self.setupFile_fontInfo(self.paths["fontInfo"])
        self.setupFile_features(self.paths["features"])

    def setupFile_outlineSource(self, path):
        """
        Make the outline source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        c = self.outlineCompilerClass(self.font, path, self.glyphOrder)
        c.compile()
        self.log += c.log

    def setupFile_menuName(self, path):
        """
        Make the menu name source file. This gets the values for
        the file using the fallback system as described below:

        ====  ===
        [PS]  postscriptFontName
        f=    openTypeNamePreferredFamilyName
        s=    openTypeNamePreferredSubfamilyName
        l=    styleMapFamilyName
        m=1,  openTypeNameCompatibleFullName
        ====  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        psName = getAttrWithFallback(self.font.info, "postscriptFontName")
        lines = [
            "[%s]" % psName
        ]
        # family name
        familyName = getAttrWithFallback(self.font.info, "openTypeNamePreferredFamilyName")
        encodedFamilyName = winStr(familyName)
        lines.append("f=%s" % encodedFamilyName)
        if encodedFamilyName != familyName:
            lines.append("f=1,%s" % macStr(familyName))
        # style name
        styleName = getAttrWithFallback(self.font.info, "openTypeNamePreferredSubfamilyName")
        encodedStyleName = winStr(styleName)
        lines.append("s=%s" % encodedStyleName)
        if encodedStyleName != styleName:
            lines.append("s=1,%s" % macStr(styleName))
        # compatible name
        winCompatible = getAttrWithFallback(self.font.info, "styleMapFamilyName")
        # the second qualification here is in place for Mac Office <= 2004.
        # in that app the menu name is pulled from name ID 18. the font
        # may have standard naming data that combines to a length longer
        # than the app can handle (see Adobe Tech Note #5088). the designer
        # may have created a specific openTypeNameCompatibleFullName to
        # get around this problem. sigh, old app bugs live long lives.
        if winCompatible != familyName or self.font.info.openTypeNameCompatibleFullName is not None:
            # windows
            line = "l=%s" % normalizeStringForPostscript(winCompatible)
            lines.append(line)
            # mac
            macCompatible = getAttrWithFallback(self.font.info, "openTypeNameCompatibleFullName")
            line = "m=1,%s" % macStr(macCompatible)
            lines.append(line)
        text = "\n".join(lines) + "\n"
        f = open(path, "wb")
        f.write(toBytestoBytes(text))
        f.close()

    def setupFile_glyphOrder(self, path):
        """
        Make the glyph order source file.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        lines = []
        for designName in self.glyphOrder:
            finalName = self.glyphDesignNameToFinalNameMap[designName]
            if designName in self.font and self.font[designName].unicode is not None:
                codes = self.font[designName].unicodes
                unicodes = []
                for code in codes:
                    code = "%04X" % code
                    if len(code) <= 4:
                        code = "uni%s" % code
                    else:
                        code = "u%s" % code
                    unicodes.append(code)
                unicodes = ",".join(unicodes)
                line = "%s %s %s" % (finalName, designName, unicodes)
            else:
                line = "%s %s" % (finalName, designName)
            lines.append(line)
        text = "\n".join(lines) + "\n"
        f = open(path, "wb")
        f.write(toBytes(text))
        f.close()

    def setupFile_fontInfo(self, path):
        """
        Make the font info source file. This gets the values for
        the file using the fallback system as described below:

        ==========================  ===
        IsItalicStyle               styleMapStyleName
        IsBoldStyle                 styleMapStyleName
        PreferOS/2TypoMetrics       openTypeOS2Selection
        IsOS/2WidthWeigthSlopeOnly  openTypeOS2Selection
        IsOS/2OBLIQUE               openTypeOS2Selection
        ==========================  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        lines = []
        # style mapping
        styleMapStyleName = getAttrWithFallback(self.font.info, "styleMapStyleName")
        if styleMapStyleName in ("italic", "bold italic"):
            lines.append("IsItalicStyle true")
        else:
            lines.append("IsItalicStyle false")
        if styleMapStyleName in ("bold", "bold italic"):
            lines.append("IsBoldStyle true")
        else:
            lines.append("IsBoldStyle false")
        # fsSelection bits
        selection = getAttrWithFallback(self.font.info, "openTypeOS2Selection")
        if 7 in selection:
            lines.append("PreferOS/2TypoMetrics true")
        else:
            lines.append("PreferOS/2TypoMetrics false")
        if 8 in selection:
            lines.append("IsOS/2WidthWeigthSlopeOnly true")
        else:
            lines.append("IsOS/2WidthWeigthSlopeOnly false")
        if 9 in selection:
            lines.append("IsOS/2OBLIQUE true")
        else:
            lines.append("IsOS/2OBLIQUE false")
        # write the file
        if lines:
            f = open(path, "wb")
            f.write(toBytes("\n".join(lines)))
            f.close()

    def setupFile_features(self, path):
        """
        Make the features source file. If any tables
        or the kern feature are defined in the font's
        features, they will not be overwritten.

        **This should not be called externally.** Subclasses
        may override this method to handle the file creation
        in a different way if desired.
        """
        # force absolute includes into the features
        if self.font.path is None:
            existingFeaturePath = None
            existing = self.font.features.text
            if existing is None:
                existing = ""
        elif self.features is not None:
            existingFeaturePath = os.path.normpath(os.path.join(self.font.path, self.features))
            with open(existingFeaturePath, "r", encoding="utf-8") as fea:
                text = fea.read()
            existing = forceAbsoluteIncludesInFeatures(text, os.path.dirname(existingFeaturePath))
        else:
            existingFeaturePath = os.path.join(self.font.path, "features.fea")
            existing = forceAbsoluteIncludesInFeatures(self.font.features.text, os.path.dirname(self.font.path))
        # break the features into parts
        features, tables = extractFeaturesAndTables(existing, scannedFiles=[existingFeaturePath])
        # build tables that are not in the existing features
        autoTables = {}
        if "head" not in tables:
            autoTables["head"] = self.writeFeatures_head()
        if "hhea" not in tables:
            autoTables["hhea"] = self.writeFeatures_hhea()
        if "OS/2" not in tables:
            autoTables["OS/2"] = self.writeFeatures_OS2()
        if "name" not in tables:
            autoTables["name"] = self.writeFeatures_name()
        # build the kern feature if necessary
        autoFeatures = {}
        if "kern" not in features and len(self.font.kerning):
            autoFeatures["kern"] = self.writeFeatures_kern()
        # write the features
        features = [existing]
        for name, text in sorted(autoFeatures.items()):
            features.append(text)
        for name, text in sorted(autoTables.items()):
            features.append(text)
        features = "\n\n".join(features)
        # write the result
        f = open(path, "wb")
        f.write(toBytes(features))
        f.close()

    def writeFeatures_kern(self):
        """
        Write the kern feature to a string and return it.

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        writer = KernFeatureWriter(self.font)
        return writer.write()

    def writeFeatures_head(self):
        """
        Write the head to a string and return it.

        This gets the values for the file using the fallback
        system as described below:

        =====  ===
        X.XXX  versionMajor.versionMinor
        =====  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        versionMajor = getAttrWithFallback(self.font.info, "versionMajor")
        versionMinor = getAttrWithFallback(self.font.info, "versionMinor")
        value = "%d.%s" % (versionMajor, str(versionMinor).zfill(3))
        writer = FeatureTableWriter("head")
        writer.addLineWithKeyValue("FontRevision", value)
        return writer.write()

    def writeFeatures_hhea(self):
        """
        Write the hhea to a string and return it.

        This gets the values for the file using the fallback
        system as described below:

        ===========  ===
        Ascender     openTypeHheaAscender
        Descender    openTypeHheaDescender
        LineGap      openTypeHheaLineGap
        CaretOffset  openTypeHheaCaretOffset
        ===========  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        ascender = getAttrWithFallback(self.font.info, "openTypeHheaAscender")
        descender = getAttrWithFallback(self.font.info, "openTypeHheaDescender")
        lineGap = getAttrWithFallback(self.font.info, "openTypeHheaLineGap")
        caret = getAttrWithFallback(self.font.info, "openTypeHheaCaretOffset")
        writer = FeatureTableWriter("hhea")
        writer.addLineWithKeyValue("Ascender", _roundInt(ascender))
        writer.addLineWithKeyValue("Descender", _roundInt(descender))
        writer.addLineWithKeyValue("LineGap", _roundInt(lineGap))
        writer.addLineWithKeyValue("CaretOffset", _roundInt(caret))
        return writer.write()

    def writeFeatures_name(self):
        """
        Write the name to a string and return it.

        This gets the values for the file using the fallback
        system as described below:

        =========  ===
        nameid 0   copyright
        nameid 7   trademark
        nameid 8   openTypeNameManufacturer
        nameid 9   openTypeNameDesigner
        nameid 10  openTypeNameDescription
        nameid 11  openTypeNameManufacturerURL
        nameid 12  openTypeNameDesignerURL
        nameid 13  openTypeNameLicense
        nameid 14  openTypeNameLicenseURL
        nameid 19  openTypeNameSampleText
        =========  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        idToAttr = [
            (0  , "copyright"),
            (7  , "trademark"),
            (8  , "openTypeNameManufacturer"),
            (9  , "openTypeNameDesigner"),
            (10 , "openTypeNameDescription"),
            (11 , "openTypeNameManufacturerURL"),
            (12 , "openTypeNameDesignerURL"),
            (13 , "openTypeNameLicense"),
            (14 , "openTypeNameLicenseURL"),
            (19 , "openTypeNameSampleText")
        ]
        lines = []
        for id, attr in idToAttr:
            value = getAttrWithFallback(self.font.info, attr)
            if value is None:
                continue
            s = 'nameid %d "%s";' % (id, winStr(value))
            lines.append(s)
            s = 'nameid %d 1 "%s";' % (id, macStr(value))
            lines.append(s)
        if self.font.info.openTypeNameRecords is not None:
            for record in self.font.info.openTypeNameRecords:
                nameID = record["nameID"]
                if nameID >= 1 and nameID <= 6:
                    continue
                platformID = record["platformID"]
                if platformID not in (1, 3):
                    continue
                encodingID = record["encodingID"]
                languageID = record["languageID"]
                string = record["string"]
                if platformID == 1:
                    string = macStr(string)
                else:
                    string = winStr(string)
                s = 'nameid %d %d %d %d "%s";' % (nameID, platformID, encodingID, languageID, string)
                lines.append(s)
        if not lines:
            return ""
        writer = FeatureTableWriter("name")
        for line in lines:
            writer.addLine(line)
        return writer.write()

    def writeFeatures_OS2(self):
        """
        Write the OS/2 to a string and return it.

        This gets the values for the file using the fallback
        system as described below:

        =============  ===
        FSType         openTypeOS2Type
        Panose         openTypeOS2Panose
        UnicodeRange   openTypeOS2UnicodeRanges
        CodePageRange  openTypeOS2CodePageRanges
        TypoAscender   openTypeOS2TypoAscender
        TypoDescender  openTypeOS2TypoDescender
        TypoLineGap    openTypeOS2TypoLineGap
        winAscent      openTypeOS2WinAscent
        winDescent     openTypeOS2WinDescent
        XHeight        xHeight
        CapHeight      capHeight
        WeightClass    openTypeOS2WeightClass
        WidthClass     openTypeOS2WidthClass
        Vendor         openTypeOS2VendorID
        =============  ===

        **This should not be called externally.** Subclasses
        may override this method to handle the string creation
        in a different way if desired.
        """
        codePageBitTranslation = {
            0  : "1252",
            1  : "1250",
            2  : "1251",
            3  : "1253",
            4  : "1254",
            5  : "1255",
            6  : "1256",
            7  : "1257",
            8  : "1258",
            16 : "874",
            17 : "932",
            18 : "936",
            19 : "949",
            20 : "950",
            21 : "1361",
            48 : "869",
            49 : "866",
            50 : "865",
            51 : "864",
            52 : "863",
            53 : "862",
            54 : "861",
            55 : "860",
            56 : "857",
            57 : "855",
            58 : "852",
            59 : "775",
            60 : "737",
            61 : "708",
            62 : "850",
            63 : "437"
        }
        # writer
        writer = FeatureTableWriter("OS/2")
        # type
        writer.addLineWithKeyValue("FSType", intListToNum(getAttrWithFallback(self.font.info, "openTypeOS2Type"), 0, 16))
        # panose
        panose = [str(i) for i in getAttrWithFallback(self.font.info, "openTypeOS2Panose")]
        writer.addLineWithKeyValue("Panose", " ".join(panose))
        # unicode ranges
        unicodeRange = [str(i) for i in getAttrWithFallback(self.font.info, "openTypeOS2UnicodeRanges")]
        if unicodeRange:
            writer.addLineWithKeyValue("UnicodeRange", " ".join(unicodeRange))
        # code page ranges
        codePageRange = [codePageBitTranslation[i] for i in getAttrWithFallback(self.font.info, "openTypeOS2CodePageRanges") if i in codePageBitTranslation]
        if codePageRange:
            writer.addLineWithKeyValue("CodePageRange", " ".join(codePageRange))
        # vertical metrics
        writer.addLineWithKeyValue("TypoAscender", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoAscender")))
        writer.addLineWithKeyValue("TypoDescender", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoDescender")))
        writer.addLineWithKeyValue("TypoLineGap", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2TypoLineGap")))
        writer.addLineWithKeyValue("winAscent", _roundInt(getAttrWithFallback(self.font.info, "openTypeOS2WinAscent")))
        writer.addLineWithKeyValue("winDescent", abs(_roundInt(getAttrWithFallback(self.font.info, "openTypeOS2WinDescent"))))
        writer.addLineWithKeyValue("XHeight", _roundInt(getAttrWithFallback(self.font.info, "xHeight")))
        writer.addLineWithKeyValue("CapHeight", _roundInt(getAttrWithFallback(self.font.info, "capHeight")))
        writer.addLineWithKeyValue("WeightClass", getAttrWithFallback(self.font.info, "openTypeOS2WeightClass"))
        writer.addLineWithKeyValue("WidthClass", getAttrWithFallback(self.font.info, "openTypeOS2WidthClass"))
        writer.addLineWithKeyValue("Vendor", '"%s"' % getAttrWithFallback(self.font.info, "openTypeOS2VendorID"))
        return writer.write()


# -----------
# Glyph Names
# -----------

_digits = set("0123456789")
_validCharacters = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.")


def isLegalGlyphName(glyphName):
    """
    >>> isLegalGlyphName("a")
    True
    >>> isLegalGlyphName(".foo")
    False
    >>> isLegalGlyphName(".notdef")
    True
    >>> isLegalGlyphName("foo.bar")
    True
    >>> isLegalGlyphName("1foo")
    False
    >>> isLegalGlyphName("foo1")
    True
    >>> isLegalGlyphName("f*o")
    False
    >>> isLegalGlyphName("f$o")
    False
    >>> isLegalGlyphName("abcdefghijklmnopqrstuvwxyz01234")
    True
    >>> isLegalGlyphName("abcdefghijklmnopqrstuvwxyz012345")
    False
    """
    # must not start with a digit or period
    if glyphName[0] in _digits:
        return False
    if glyphName[0] == "." and glyphName != ".notdef":
        return False
    # up to 31 characters in length
    if len(glyphName) > 31:
        return False
    # must be entirely comprised of characters from A-Z a-z 0-9 . _
    for character in glyphName:
        if character not in _validCharacters:
            return False
    # passed
    return True


def normalizeGlyphName(glyphName, uniValue, existing):
    """
    >>> normalizeGlyphName("a-b-c", None, [])
    'abc'
    >>> normalizeGlyphName("a*b*c", None, [])
    'abc'
    >>> normalizeGlyphName("a$b$c", None, [])
    'abc'
    >>> normalizeGlyphName("a-b-c", None, ["abc"])
    'abc.1'
    >>> normalizeGlyphName("!", int("0021", 16), [])
    'uni0021'
    >>> normalizeGlyphName("!", int("0021", 16), ['uni0021'])
    'uni0021.1'
    >>> normalizeGlyphName("?", int("003F", 16), [])
    'uni003F'
    >>> normalizeGlyphName("?", int("003F", 16), ['uni003F'])
    'uni003F.1'
    >>> normalizeGlyphName("abcdefghijklmnopqrstuvwxyz01234", None, [])
    'abcdefghijklmnopqrstuvwxyz01234'
    >>> normalizeGlyphName("abcdefghijklmnopqrstuvwxyz012345", None, [])
    'glyph1'
    >>> normalizeGlyphName("abcdefghijklmnopqrstuvwxyz0123456", None, ["glyph1"])
    'glyph2'
    """
    # convert to unicode
    glyphName = unicode(glyphName)
    # remove illegal characters
    glyphName = unicodedata.normalize("NFKD", glyphName)
    glyphName = "".join([c for c in glyphName if c in _validCharacters])
    # no new name
    if not glyphName:
        # quickly try to apply the adobe standard
        if uniValue:
            if uniValue > 0x0000 and uniValue < 0xFFFF:
                prefix = "uni"
            else:
                prefix = "u"
            glyphName = prefix + hex(uniValue)[2:].zfill(4).upper()
    # hit test
    if glyphName in existing:
        glyphName = _makeUniqueGlyphName(glyphName, existing)
    # test for validity
    if not isLegalGlyphName(glyphName):
        glyphName = None
    # fallback
    if not glyphName:
        glyphName = _makeUniqueFallbackGlyphName(existing)
    return glyphName


def _makeUniqueGlyphName(glyphName, existing, number=1):
    """
    _makeUniqueGlyphName("abc", ["abc"])
    'abc.1'
    """
    newName = "%s.%d" % (glyphName, number)
    if newName in existing:
        return _makeUniqueGlyphName(glyphName, existing, number + 1)
    return newName


def _makeUniqueFallbackGlyphName(existing, number=1):
    """
    >>> _makeUniqueFallbackGlyphName([])
    'glyph1'
    >>> _makeUniqueFallbackGlyphName(["glyph1"])
    'glyph2'
    """
    assert number < 100000  # arbitrary, but come on. 100,000 illegal glyph names?
    name = "glyph%d" % number
    if name in existing:
        return _makeUniqueFallbackGlyphName(existing, number + 1)
    return name


# --------
# Features
# --------

includeRE = re.compile(
    "(include\s*\(\s*)"
    "([^\)]+)"
    "(\s*\))"  # this won't actually capture a trailing space.
)

forceAbsoluteIncludesInFeaturesTestText = """
# absolute path
include(/Users/bob/foo1/bar1/default.fea);

# relative path
include(foo2/bar2/default.fea);

# . syntax
include(./foo3/bar3/default.fea);

# .. syntax
include(../foo4/bar4/default.fea);

# spaces around path
include( foo5/bar5/default.fea );
"""

forceAbsoluteIncludesInFeaturesTestResult = """
# absolute path
include(/Users/bob/foo1/bar1/default.fea);

# relative path
include(/test1/test2/foo2/bar2/default.fea);

# . syntax
include(/test1/test2/foo3/bar3/default.fea);

# .. syntax
include(/test1/foo4/bar4/default.fea);

# spaces around path
include( /test1/test2/foo5/bar5/default.fea );
"""


def forceAbsoluteIncludesInFeatures(text, directory):
    """
    Convert relative includes in the *text*
    to absolute includes.

    >>> result = forceAbsoluteIncludesInFeatures(forceAbsoluteIncludesInFeaturesTestText, "/test1/test2")
    >>> result == forceAbsoluteIncludesInFeaturesTestResult
    True
    """
    for match in reversed(list(includeRE.finditer(text))):
        start, includePath, close = match.groups()
        # absolute path
        if os.path.isabs(includePath):
            continue
        # relative path
        currentDirectory = directory
        parts = includePath.split(os.sep)
        for index, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            # .. = up one level
            if part == "..":
                currentDirectory = os.path.dirname(currentDirectory)
            # . = current level
            elif part == ".":
                continue
            else:
                break
        subPath = os.sep.join(parts[index:])
        srcPath = os.path.join(currentDirectory, subPath)
        includeText = start + srcPath + close
        text = text[:match.start()] + includeText + text[match.end():]
    return text


def _roundInt(value):
    return int(round(value))


# ----------------------
# Basic Feature Splitter
# ----------------------

stringRE = re.compile(
    "(\"[^$\"]*\")"
)
featureTableStartRE = re.compile(
    "("
    "feature"
    "\s+"
    "\S{4}"
    "\s*"
    "\{"
    "|"
    "table"
    "\s+"
    "\S{4}"
    "\s*"
    "\{"
    ")",
    re.MULTILINE
)
featureNameRE = re.compile(
    "feature"
    "\s+"
    "(\S{4})"
    "\s*"
    "\{"
)
tableNameRE = re.compile(
    "table"
    "\s+"
    "(\S{4})"
    "\s*"
    "\{"
)


def extractFeaturesAndTables(text, scannedFiles=[]):
    # strip all comments
    decommentedLines = [line.split("#")[0] for line in text.splitlines()]
    text = "\n".join(decommentedLines)
    # replace all strings with temporary placeholders.
    destringedLines = []
    stringReplacements = {}
    for line in text.splitlines():
        if "\"" in line:
            line = line.replace("\\\"", "__ufo2fdk_temp_escaped_quote__")
            for found in stringRE.findall(line):
                temp = "__ufo2fdk_temp_string_%d__" % len(stringReplacements)
                line = line.replace(found, temp, 1)
                stringReplacements[temp] = found.replace("__ufo2fdk_temp_escaped_quote__", "\\\"")
            line = line.replace("__ufo2fdk_temp_escaped_quote__", "\\\"")
        destringedLines.append(line)
    text = "\n".join(destringedLines)
    # extract all includes
    includes = []
    for match in includeRE.finditer(text):
        start, includePath, close = match.groups()
        includes.append(includePath)
    # slice off the text that comes before
    # the first feature/table definition
    startMatch = featureTableStartRE.search(text)
    if startMatch is not None:
        start, end = startMatch.span()
        text = text[start:]
    else:
        text = ""
    # break the features
    broken = _textBreakRecurse(text)
    # organize into tables and features
    features = {}
    tables = {}
    for text in broken:
        text = text.strip()
        if not text:
            continue
        # replace the strings
        finalText = text
        for temp, original in list(stringReplacements.items()):
            if temp in finalText:
                del stringReplacements[temp]
                finalText = finalText.replace(temp, original, 1)
        finalText = finalText.strip()
        # grab feature or table names and store
        featureMatch = featureNameRE.search(text)
        if featureMatch is not None:
            features[featureMatch.group(1)] = finalText
        else:
            tableMatch = tableNameRE.search(text)
            tables[tableMatch.group(1)] = finalText
    # scan all includes
    for path in includes:
        if path in scannedFiles:
            continue
        scannedFiles.append(path)
        if os.path.exists(path):
            f = open(path, "r", encoding="utf-8")
            text = f.read()
            f.close()
            f, t = extractFeaturesAndTables(text, scannedFiles)
            features.update(f)
            tables.update(t)
    return features, tables


def _textBreakRecurse(text):
    matched = []
    match = featureTableStartRE.search(text)
    if match is None:
        matched.append(text)
    else:
        start, end = match.span()
        # add any preceding text to the previous item
        if start != 0:
            precedingText = matched.pop(0)
            precedingText += text[:start]
            matched.insert(0, precedingText)
        # look ahead to see if there is another feature
        next = text[end:]
        nextMatch = featureTableStartRE.search(next)
        if nextMatch is None:
            # if nothing has been found, add
            # the remaining text to the feature
            matchedText = text[start:]
            matched.append(matchedText)
        else:
            # if one has been found, grab all text
            # from before the feature start and add
            # it to the current feature.
            nextStart, nextEnd = nextMatch.span()
            matchedText = text[:end + nextStart]
            matched.append(matchedText)
            # recurse through the remaining text
            matched += _textBreakRecurse(next[nextStart:])
    return matched


extractFeaturesAndTablesTestText = """
@foo = [bar];

# test commented item
#feature fts1 {
#    sub foo by bar;
#} fts1;

feature fts2 {
    sub foo by bar;
} fts2;

table tts1 {
    nameid 1 "feature this { is not really a \\\"feature that { other thing is";
} tts1;feature fts3 { sub a by b;} fts3;
"""

extractFeaturesAndTablesTestResult = (
    {
        'fts2': 'feature fts2 {\n    sub foo by bar;\n} fts2;',
        'fts3': 'feature fts3 { sub a by b;} fts3;'
    },
    {
        'tts1': 'table tts1 {\n    nameid 1 "feature this { is not really a \\"feature that { other thing is";\n} tts1;'
    }
)


def testBreakFeaturesAndTables():
    """
    >>> r = extractFeaturesAndTables(extractFeaturesAndTablesTestText)
    >>> r == extractFeaturesAndTablesTestResult
    True
    """


if __name__ == "__main__":
    import doctest
    doctest.testmod()
