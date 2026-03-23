"""
Spell-check highlighter for QTextEdit using pyspellchecker.

Usage:
    highlighter = SpellCheckHighlighter(editor.document())

Right-click suggestions are handled via a context-menu helper:
    apply_spell_context_menu(editor)
"""

import re
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QTextCursor
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt

# Words known to the Book of Mormon / KJV vocabulary that pyspellchecker
# would otherwise flag as misspelled.
_SCRIPTURE_WORDS = {
    'abinadi', 'ahah', 'ahaz', 'akish', 'amaleki', 'amalekites',
    'amalickiah', 'amalickiahites', 'aminadab', 'aminadi', 'amlici',
    'amlicites', 'ammaron', 'ammonihah', 'ammoron', 'amnigaddah', 'amnor',
    'amulek', 'amulon', 'amulonites', 'antionum', 'antiparah', 'antipus',
    'appeareth', 'ascendeth', 'asketh', 'atoneth', 'availeth', 'beareth',
    'becometh', 'beginneth', 'beholdest', 'behooveth', 'believest',
    'believeth', 'belongeth', 'bloodsheds', 'bringeth', 'buildeth',
    'causeth', 'ceaseth', 'cezoram', 'chemish', 'cimeter', 'cimeters',
    'claimeth', 'cohor', 'cometh', 'commandeth', 'condemneth', 'corianton',
    'coriantor', 'coriantum', 'coriantumr', 'corihor', 'corom', 'cumeni',
    'cumorah', 'deceivings', 'defence', 'delighteth', 'delightsome',
    'denieth', 'desirest', 'desireth', 'destructions', 'dieth', 'doeth',
    'draweth', 'drinketh', 'dwelleth', 'eateth', 'emer', 'endeth',
    'endureth', 'engraven', 'enticeth', 'envyings', 'ethem', 'fighteth',
    'findeth', 'fulfilleth', 'gadianton', 'gathereth', 'giddianhi',
    'gidgiddoni', 'gilgal', 'giveth', 'goeth', 'grieveth', 'groanings',
    'hearkeneth', 'hearthom', 'helaman', 'hideth', 'himni', 'howlings',
    'humbleth', 'inviteth', 'ishmaelites', 'jarom', 'jershon', 'josephites',
    'journeyings', 'justifieth', 'kib', 'kindreds', 'kishkumen', 'knocketh',
    'knowest', 'knoweth', 'korihor', 'lachoneus', 'laman', 'lamanite',
    'lamanites', 'lamoni', 'leadeth', 'lehi', 'lehonti', 'lemuelites',
    'lieth', 'limhi', 'listeth', 'liveth', 'loveth', 'lyings', 'maketh',
    'manti', 'mattereth', 'meaneth', 'melek', 'middoni', 'mightest',
    'morianton', 'moronihah', 'mosiah', 'mulek', 'nehor', 'nehors', 'nephi',
    'nephihah', 'nephite', 'nephites', 'omner', 'onidah', 'orihah', 'pachus',
    'pacumeni', 'pahoran', 'perisheth', 'persuadeth', 'plunderings',
    'prepareth', 'profiteth', 'putteth', 'receiveth', 'reigneth', 'rejoiceth',
    'remaineth', 'remaliah', 'rememberest', 'remembereth', 'repenteth',
    'rezin', 'riplakish', 'sariah', 'sayest', 'sebus', 'seeketh', 'seemeth',
    'seest', 'seeth', 'seezoram', 'sendeth', 'senine', 'senum', 'seon',
    'sepulchre', 'serveth', 'shem', 'sherem', 'sherrizah', 'shez',
    'shiblom', 'shiblon', 'shiz', 'showeth', 'shule', 'sidom', 'speaketh',
    'sprouteth', 'standeth', 'stiffnecked', 'stiffneckedness', 'stirreth',
    'strifes', 'suffereth', 'sufficeth', 'supposeth', 'swelleth', 'taketh',
    'teacheth', 'teancum', 'teomner', 'testifieth', 'thinketh', 'threatenings',
    'thunderings', 'worketh', 'zarahemla', 'zeezrom', 'zemnarihah', 'zenock',
    'zenos', 'zerahemnah', 'zoram', 'zoramites',
    # Common KJV / archaic words
    'hath', 'doth', 'wilt', 'thou', 'thee', 'thine', 'thy', 'ye', 'yea',
    'nay', 'unto', 'hitherto', 'thereof', 'therein', 'hereby', 'wherein',
    'whereby', 'whosoever', 'whatsoever', 'howbeit', 'inasmuch', 'insomuch',
    'behold', 'thus', 'saith', 'verily', 'aforetime', 'twain',
}

_WORD_RE = re.compile(r"[A-Za-z']+")

# Lazily initialised so import cost is zero when spell check isn't used
_checker = None


def _get_checker():
    global _checker
    if _checker is None:
        from spellchecker import SpellChecker
        _checker = SpellChecker()
        _checker.word_frequency.load_words(_SCRIPTURE_WORDS)
    return _checker


def _is_misspelled(word: str) -> bool:
    """Return True if word is misspelled (ignoring pure-apostrophe tokens)."""
    bare = word.strip("'")
    if not bare or not bare.isalpha():
        return False
    return bare.lower() not in _get_checker()


class SpellCheckHighlighter(QSyntaxHighlighter):
    """Underlines misspelled words in a QTextDocument with a red squiggle."""

    def __init__(self, document):
        super().__init__(document)
        self._fmt = QTextCharFormat()
        self._fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self._fmt.setUnderlineColor(QColor("#f38ba8"))  # theme RED

    def highlightBlock(self, text: str):
        checker = _get_checker()
        for m in _WORD_RE.finditer(text):
            word = m.group()
            bare = word.strip("'")
            if bare and bare.isalpha() and bare.lower() not in checker:
                self.setFormat(m.start(), len(word), self._fmt)


def apply_spell_context_menu(editor):
    """
    Monkey-patch a QTextEdit to add spell-check suggestions to its
    right-click context menu.  Call once after the editor is created.
    """
    original_menu = editor.createStandardContextMenu

    def _custom_menu(pos=None):
        menu = original_menu() if pos is None else original_menu(pos)

        cursor = editor.cursorForPosition(pos) if pos is not None else editor.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip("'")

        if word and word.isalpha() and _is_misspelled(word):
            checker = _get_checker()
            suggestions = list(checker.candidates(word) or [])[:6]

            if suggestions:
                menu.insertSeparator(menu.actions()[0] if menu.actions() else None)
                suggestion_menu = QMenu(f'Spelling: "{word}"', menu)
                suggestion_menu.setStyleSheet(menu.styleSheet())
                for suggestion in sorted(suggestions):
                    act = suggestion_menu.addAction(suggestion)
                    act.triggered.connect(
                        lambda checked=False, c=cursor, s=suggestion: _replace_word(editor, c, s)
                    )
                menu.insertMenu(menu.actions()[0] if menu.actions() else None, suggestion_menu)
                menu.insertSeparator(menu.actions()[1] if len(menu.actions()) > 1 else None)

        return menu

    editor.createStandardContextMenu = _custom_menu


def _replace_word(editor, cursor: QTextCursor, replacement: str):
    cursor.insertText(replacement)
    editor.setTextCursor(cursor)
