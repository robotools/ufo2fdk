# -*- coding: utf8 -*-

try:
    set
except NameError:
    from sets import Set as set

try:
    sorted
except NameError:
    def sorted(l):
        l = list(l)
        l.sort()
        return l

inlineGroupInstance = (list, tuple, set)

side1Prefix = "public.kern1."
side2Prefix = "public.kern2."
side1FeaPrefix = "@kern1."
side2FeaPrefix = "@kern2."
groupPrefixLength = len(side1Prefix)
classPrefixLength = len(side1FeaPrefix)


class KernFeatureWriter(object):

    """
    This object will create a kerning feature in FDK
    syntax using the kerning in the given font. The
    only external method is :meth:`ufo2fdk.tools.kernFeatureWriter.write`.
    """

    def __init__(self, font, groupNamePrefix=""):
        if groupNamePrefix:
            from warnings import warn
            warn("The groupNamePrefix argument is no longer used.", DeprecationWarning)
        self.font = font
        self.getGroups()
        self.getPairs()
        self.applyGroupNameToClassNameMapping()
        self.getFlatGroups()

    def write(self, headerText=None):
        """
        Write the feature text. If *headerText* is provided
        it will inserted after the ``feature kern {`` line.
        """
        if not self.pairs:
            return ""
        glyphGlyph, glyphGroupDecomposed, groupGlyphDecomposed, glyphGroup, groupGlyph, groupGroup = self.getSeparatedPairs(self.pairs)
        # write the classes
        groups = dict(self.side1Groups)
        groups.update(self.side2Groups)
        classes = self.getClassDefinitionsForGroups(groups)
        # write the kerning rules
        rules = []
        order = [
            ("# glyph, glyph", glyphGlyph),
            ("# glyph, group exceptions", glyphGroupDecomposed),
            ("# group exceptions, glyph", groupGlyphDecomposed),
            ("# glyph, group", glyphGroup),
            ("# group, glyph", groupGlyph),
            ("# group, group", groupGroup),
        ]
        for note, pairs in order:
            if pairs:
                rules.append("")
                rules.append(note)
                rules += self.getFeatureRulesForPairs(pairs)
        # compile
        feature = ["feature kern {"]
        if headerText:
            for line in headerText.splitlines():
                line = line.strip()
                if not line.startswith("#"):
                    line = "# " + line
                line = "    " + line
                feature.append(line)
        for line in classes + rules:
            if line:
                line = "    " + line
            feature.append(line)
        feature.append("} kern;")
        # done
        return u"\n".join(feature)

    # -------------
    # Initial Setup
    # -------------

    def getGroups(self):
        """
        Set up two dictionaries representing first and
        second side groups.

        You should not call this method directly.
        """
        side1Groups = self.side1Groups = {}
        side2Groups = self.side2Groups = {}
        for groupName, contents in self.font.groups.items():
            contents = [glyphName for glyphName in contents if glyphName in self.font]
            if not contents:
                continue
            if groupName.startswith(side1Prefix):
                side1Groups[groupName] = contents
            elif groupName.startswith(side2Prefix):
                side2Groups[groupName] = contents

    def getPairs(self):
        """
        Set up a dictionary containing all kerning pairs.
        This should filter out pairs containing empty groups
        and groups/glyphs that are not in the font.

        You should not call this method directly.
        """
        pairs = self.pairs = {}
        for (side1, side2), value in self.font.kerning.items():
            # skip missing glyphs
            if side1 not in self.side1Groups and side1 not in self.font:
                continue
            if side2 not in self.side2Groups and side2 not in self.font:
                continue
            # skip empty groups
            if side1.startswith(side1Prefix) and side1 not in self.side1Groups:
                continue
            if side2.startswith(side2Prefix) and side2 not in self.side2Groups:
                continue
            # store pair
            pairs[side1, side2] = value

    def applyGroupNameToClassNameMapping(self):
        """
        Set up a dictionary mapping group names to class names.

        You should not call this method directly.
        """
        mapping = {}
        for groupNames, feaPrefix in ((self.side1Groups.keys(), side1FeaPrefix), (self.side2Groups.keys(), side2FeaPrefix)):
            for groupName in sorted(groupNames):
                className = feaPrefix + groupName[groupPrefixLength:]
                mapping[groupName] = makeLegalClassName(className, mapping.keys())
        # kerning
        newPairs = {}
        for (side1, side2), value in self.pairs.items():
            if side1.startswith(side1Prefix):
                side1 = mapping[side1]
            if side2.startswith(side2Prefix):
                side2 = mapping[side2]
            newPairs[side1, side2] = value
        self.pairs.clear()
        self.pairs.update(newPairs)
        # groups
        newSide1Groups = {}
        for groupName, contents in self.side1Groups.items():
            groupName = mapping[groupName]
            newSide1Groups[groupName] = contents
        self.side1Groups.clear()
        self.side1Groups.update(newSide1Groups)
        newSide2Groups = {}
        for groupName, contents in self.side2Groups.items():
            groupName = mapping[groupName]
            newSide2Groups[groupName] = contents
        self.side2Groups.clear()
        self.side2Groups.update(newSide2Groups)

    def getFlatGroups(self):
        """
        Set up two dictionaries keyed by glyph names with
        group names as values for side 1 and side 2 groups.

        You should not call this method directly.
        """
        flatSide1Groups = self.flatSide1Groups = {}
        flatSide2Groups = self.flatSide2Groups = {}
        for groupName, glyphList in self.side1Groups.items():
            for glyphName in glyphList:
                # user has glyph in more than one group.
                # this is not allowed.
                if glyphName in flatSide1Groups:
                    continue
                flatSide1Groups[glyphName] = groupName
        for groupName, glyphList in self.side2Groups.items():
            for glyphName in glyphList:
                # user has glyph in more than one group.
                # this is not allowed.
                if glyphName in flatSide2Groups:
                    continue
                flatSide2Groups[glyphName] = groupName

    # ------------
    # Pair Support
    # ------------

    def isHigherLevelPairPossible(self, pair):
        """
        Determine if there is a higher level pair possible.
        This doesn't indicate that the pair exists, it simply
        indicates that something higher than (side1, side2)
        can exist.

        You should not call this method directly.
        """
        side1, side2 = pair
        if side1.startswith(side1FeaPrefix):
            side1Group = side1
            side1Glyph = None
        else:
            side1Group = self.flatSide1Groups.get(side1)
            side1Glyph = side1
        if side2.startswith(side2FeaPrefix):
            side2Group = side2
            side2Glyph = None
        else:
            side2Group = self.flatSide2Groups.get(side2)
            side2Glyph = side2

        havePotentialHigherLevelPair = False
        if side1.startswith(side1FeaPrefix) and side2.startswith(side2FeaPrefix):
            pass
        elif side1.startswith(side1FeaPrefix):
            if side2Group is not None:
                if (side1, side2) in self.pairs:
                    havePotentialHigherLevelPair = True
        elif side2.startswith(side2FeaPrefix):
            if side1Group is not None:
                if (side1, side2) in self.pairs:
                    havePotentialHigherLevelPair = True
        else:
            if side1Group is not None and side2Group is not None:
                if (side1Glyph, side2Glyph) in self.pairs:
                    havePotentialHigherLevelPair = True
                elif (side1Group, side2Glyph) in self.pairs:
                    havePotentialHigherLevelPair = True
                elif (side1Glyph, side2Group) in self.pairs:
                    havePotentialHigherLevelPair = True
            elif side1Group is not None:
                if (side1Glyph, side2Glyph) in self.pairs:
                    havePotentialHigherLevelPair = True
            elif side2Group is not None:
                if (side1Glyph, side2Glyph) in self.pairs:
                    havePotentialHigherLevelPair = True
        return havePotentialHigherLevelPair

    def getSeparatedPairs(self, pairs):
        """
        Organize *pair* into the following groups:

        * glyph, glyph
        * glyph, group (decomposed)
        * group, glyph (decomposed)
        * glyph, group
        * group, glyph
        * group, group

        You should not call this method directly.
        """
        # seperate pairs
        glyphGlyph = {}
        glyphGroup = {}
        glyphGroupDecomposed = {}
        groupGlyph = {}
        groupGlyphDecomposed = {}
        groupGroup = {}
        for (side1, side2), value in pairs.items():
            if side1.startswith(side1FeaPrefix) and side2.startswith(side2FeaPrefix):
                groupGroup[side1, side2] = value
            elif side1.startswith(side1FeaPrefix):
                groupGlyph[side1, side2] = value
            elif side2.startswith(side2FeaPrefix):
                glyphGroup[side1, side2] = value
            else:
                glyphGlyph[side1, side2] = value
        # handle decomposition
        allGlyphGlyph = set(glyphGlyph.keys())
        # glyph to group
        for (side1, side2), value in list(glyphGroup.items()):
            if self.isHigherLevelPairPossible((side1, side2)):
                finalRight = tuple([r for r in sorted(self.side2Groups[side2]) if (side1, r) not in allGlyphGlyph])
                for r in finalRight:
                    allGlyphGlyph.add((side1, r))
                glyphGroupDecomposed[side1, finalRight] = value
                del glyphGroup[side1, side2]
        # group to glyph
        for (side1, side2), value in list(groupGlyph.items()):
            if self.isHigherLevelPairPossible((side1, side2)):
                finalLeft = tuple([l for l in sorted(self.side1Groups[side1]) if (l, side2) not in glyphGlyph and (l, side2) not in allGlyphGlyph])
                for l in finalLeft:
                    allGlyphGlyph.add((l, side2))
                groupGlyphDecomposed[finalLeft, side2] = value
                del groupGlyph[side1, side2]
        # return the result
        return glyphGlyph, glyphGroupDecomposed, groupGlyphDecomposed, glyphGroup, groupGlyph, groupGroup

    # -------------
    # Write Support
    # -------------

    def getClassDefinitionsForGroups(self, groups):
        """
        Write class definitions to a list of strings.

        You should not call this method directly.
        """
        classes = []
        for groupName, contents in sorted(groups.items()):
            line = "%s = [%s];" % (groupName, " ".join(sorted(contents)))
            classes.append(line)
        return classes

    def getFeatureRulesForPairs(self, pairs):
        """
        Write pair rules to a list of strings.

        You should not call this method directly.
        """
        rules = []
        for (side1, side2), value in sorted(pairs.items()):
            if not side1 or not side2:
                continue
            if isinstance(side1, inlineGroupInstance) or isinstance(side2, inlineGroupInstance):
                line = "enum pos %s %s %d;"
            else:
                line = "pos %s %s %d;"
            if isinstance(side1, inlineGroupInstance):
                side1 = "[%s]" % " ".join(sorted(side1))
            if isinstance(side2, inlineGroupInstance):
                side2 = "[%s]" % " ".join(sorted(side2))
            rules.append(line % (side1, side2, value))
        return rules


# ------------------
# Class Name Creator
# ------------------

_invalidFirstCharacter = set(".0123456789")
_validCharacters = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._")


def makeLegalClassName(name, existing):
    """
    >>> makeLegalClassName("@kern1.foo", [])
    '@kern1.foo'

    invalid characters
    ------------------
    >>> makeLegalClassName(u"@kern1.f•o", [])
    '@kern1.fo'

    too long
    --------
    >>> makeLegalClassName("@kern1.abcdefghijklmnopqrstuvwxyz", [])
    '@kern1.abcdefghijklmnopqrstuvwx'

    fallback
    --------
    >>> makeLegalClassName("@kern1.", [])
    '@kern1.noTransPossible'
    >>> makeLegalClassName(u"@kern1.•", [])
    '@kern1.noTransPossible'
    """
    # slice off the prefix
    prefix = str(name[:classPrefixLength])
    name = name[classPrefixLength:]
    # only legal characters
    name = "".join([c for c in name if c in _validCharacters])
    name = str(name)
    # maximum length is 31 - prefix length
    name = name[:31 - classPrefixLength]
    # fallback
    if not name:
        name = "noTransPossible"
    # add the prefix
    name = prefix + name
    # make sure it is unique
    _makeUniqueClassName(name, existing)
    return name


def _makeUniqueClassName(name, existing, counter=0):
    """
    >>> _makeUniqueClassName("@kern1.foo", [])
    '@kern1.foo'

    >>> _makeUniqueClassName("@kern1.foo", ["@kern1.foo"])
    '@kern1.foo1'

    >>> _makeUniqueClassName("@kern1.foo", ["@kern1.foo", "@kern1.foo1", "@kern1.foo2"])
    '@kern1.foo3'

    >>> _makeUniqueClassName("@kern1.abcdefghijklmnopqrstuvwx", ["@kern1.abcdefghijklmnopqrstuvwx"])
    '@kern1.abcdefghijklmnopqrstuvw1'
    """
    # Add a number to the name if the counter is higher than zero.
    newName = name
    if counter > 0:
        c = str(counter)
        assert len(c) < 31 - classPrefixLength
        newName = newName[:31 - len(c)] + c
    # If the new name is in the existing group names, recurse.
    if newName in existing:
        return _makeUniqueClassName(name, existing, counter + 1)
    # Otherwise send back the new name.
    return newName

# ----
# Test
# ----


def _test():
    """
    >>> from fontTools.agl import AGL2UV
    >>> from defcon import Font
    >>> font = Font()
    >>> for glyphName in AGL2UV:
    ...     glyph = font.newGlyph(glyphName)
    >>> kerning = {
    ...     # various pair types
    ...     ("Agrave", "Agrave") : -100,
    ...     ("public.kern1.A", "Agrave") : -75,
    ...     ("public.kern1.A", "Aacute") : -74,
    ...     ("eight", "public.kern2.B") : -49,
    ...     ("public.kern1.A", "public.kern2.A") : -25,
    ...     ("public.kern1.D", "X") : -25,
    ...     ("X", "public.kern2.D") : -25,
    ...     # empty groups
    ...     ("public.kern1.C", "public.kern2.C") : 25,
    ...     ("C", "public.kern2.C") : 25,
    ...     ("public.kern1.C", "C") : 25,
    ...     # nonexistant glyphs
    ...     ("NotInFont", "NotInFont") : 25,
    ...     # nonexistant groups
    ...     ("public.kern1.NotInFont", "public.kern2.NotInFont") : 25,
    ... }
    >>> groups = {
    ...     "public.kern1.A" : ["A", "Aacute", "Agrave"],
    ...     "public.kern2.A" : ["A", "Aacute", "Agrave"],
    ...     "public.kern1.B" : ["B", "eight"],
    ...     "public.kern2.B" : ["B", "eight"],
    ...     "public.kern1.C" : [],
    ...     "public.kern2.C" : [],
    ...     "public.kern1.D" : ["D"],
    ...     "public.kern2.D" : ["D"],
    ...     "public.kern1.E" : ["E"],
    ...     "public.kern2.E" : ["E"],
    ... }
    >>> font.groups.update(groups)
    >>> font.kerning.update(kerning)

    >>> writer = KernFeatureWriter(font)
    >>> text = writer.write()
    >>> t1 = [line.strip() for line in text.strip().splitlines()]
    >>> t2 = [line.strip() for line in _expectedFeatureText.strip().splitlines()]
    >>> t1 == t2
    True
    """


_expectedFeatureText = """
feature kern {
    @kern1.A = [A Aacute Agrave];
    @kern1.B = [B eight];
    @kern1.D = [D];
    @kern1.E = [E];
    @kern2.A = [A Aacute Agrave];
    @kern2.B = [B eight];
    @kern2.D = [D];
    @kern2.E = [E];

    # glyph, glyph
    pos Agrave Agrave -100;

    # glyph, group exceptions
    enum pos eight [B eight] -49;

    # group exceptions, glyph
    enum pos [A Aacute] Agrave -75;
    enum pos [A Aacute Agrave] Aacute -74;

    # glyph, group
    pos X @kern2.D -25;

    # group, glyph
    pos @kern1.D X -25;

    # group, group
    pos @kern1.A @kern2.A -25;
} kern;
"""

if __name__ == "__main__":
    import doctest
    doctest.testmod()
