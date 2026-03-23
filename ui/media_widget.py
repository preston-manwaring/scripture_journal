from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QInputDialog, QSizePolicy,
    QLineEdit,
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread, QSize
from PyQt6.QtGui import QPixmap, QImage
from backend.db_api import get_media, attach_image, attach_link, get_image_bytes, delete_media
from backend.services.og_fetcher import fetch_og
from ui.themes import DARK, SURFACE, ELEVATED, OVERLAY, OVERLAY1, DIM, SUBTEXT, TEXT, ACCENT, RED, GREEN, BLUE

_BTN = "QPushButton {{ background:{bg}; color:{fg}; border:none; border-radius:4px; padding:4px 10px; font-size:12px; }}"


class _OGFetchWorker(QThread):
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            og = fetch_og(self._url)
            self.done.emit(og)
        except Exception as e:
            self.error.emit(str(e))


class MediaCard(QFrame):
    delete_requested = pyqtSignal(int)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._id = item["id"]
        self.setStyleSheet(f"""
            MediaCard {{
                background: {ELEVATED}; border: 1px solid {OVERLAY};
                border-radius: 8px;
            }}
        """)
        self.setMaximumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Thumbnail
        if item["has_image"]:
            img_data, mime = get_image_bytes(item["id"])
            if img_data:
                qimg = QImage.fromData(img_data)
                pix = QPixmap.fromImage(qimg).scaled(
                    300, 160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                thumb = QLabel()
                thumb.setPixmap(pix)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(thumb)

        if item["type"] == "link":
            title = item.get("og_title") or item.get("url", "")
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            title_label.setStyleSheet(f"color:{TEXT}; font-size:13px; font-weight:bold;")
            layout.addWidget(title_label)

            desc = item.get("og_description") or ""
            if desc:
                desc_label = QLabel(desc[:160] + ("..." if len(desc) > 160 else ""))
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet(f"color:{SUBTEXT}; font-size:11px;")
                layout.addWidget(desc_label)

            url_label = QLabel(f'<a href="{item["url"]}" style="color:{BLUE};">{item["url"][:60]}</a>')
            url_label.setOpenExternalLinks(True)
            url_label.setWordWrap(True)
            url_label.setStyleSheet("font-size:10px;")
            layout.addWidget(url_label)

        else:
            fname = item.get("filename") or "Image"
            name_label = QLabel(fname)
            name_label.setStyleSheet(f"color:{TEXT}; font-size:12px;")
            layout.addWidget(name_label)

        if item.get("caption"):
            cap = QLabel(f"\u201c{item['caption']}\u201d")
            cap.setWordWrap(True)
            cap.setStyleSheet(f"color:{DIM}; font-size:11px; font-style:italic;")
            layout.addWidget(cap)

        del_btn = QPushButton("Remove")
        del_btn.setStyleSheet(_BTN.format(bg=RED, fg=DARK))
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._id))
        layout.addWidget(del_btn)


class MediaWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book: str | None = None
        self._chapter: int | None = None
        self._verse: int | None = None
        self._og_worker: _OGFetchWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._verse_label = QLabel("No verse selected")
        self._verse_label.setStyleSheet(f"color:{DIM}; font-size:12px; font-style:italic;")
        layout.addWidget(self._verse_label)

        # ── Action bar ────────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        img_btn = QPushButton("Attach Image...")
        img_btn.setStyleSheet(_BTN.format(bg=ACCENT, fg="white"))
        img_btn.clicked.connect(self._on_attach_image)
        action_row.addWidget(img_btn)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("Paste URL...")
        self._url_edit.setStyleSheet(
            f"QLineEdit {{ background:{ELEVATED}; color:{TEXT}; border:1px solid {OVERLAY1};"
            f" border-radius:4px; padding:4px 8px; font-size:12px; }}"
        )
        self._url_edit.returnPressed.connect(self._on_attach_link)
        action_row.addWidget(self._url_edit)

        self._link_btn = QPushButton("Add Link")
        self._link_btn.setStyleSheet(_BTN.format(bg=BLUE, fg=DARK))
        self._link_btn.clicked.connect(self._on_attach_link)
        action_row.addWidget(self._link_btn)
        layout.addLayout(action_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        layout.addWidget(self._status_label)

        # ── Scroll area for cards ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background:{DARK}; border:none; }}")

        self._cards_container = QWidget()
        self._cards_container.setStyleSheet(f"background:{DARK};")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_verse(self, book: str, chapter: int, verse: int):
        self._book = book
        self._chapter = chapter
        self._verse = verse
        self._verse_label.setText(f"{book} {chapter}:{verse}")
        self._status_label.setText("")
        self._refresh()

    # ── Private ───────────────────────────────────────────────────────────────

    def _refresh(self):
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._book is None:
            return

        items = get_media(self._book, self._chapter, self._verse)
        for item in items:
            card = MediaCard(item)
            card.delete_requested.connect(self._on_delete)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _on_delete(self, media_id: int):
        delete_media(media_id)
        self._refresh()
        self.changed.emit()

    def _on_attach_image(self):
        if self._book is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )
        if not path:
            return
        caption, ok = QInputDialog.getText(self, "Caption", "Optional caption:")
        attach_image(
            self._book, self._chapter, self._verse,
            path, caption.strip() or None,
        )
        self._refresh()
        self.changed.emit()

    def _on_attach_link(self):
        if self._book is None:
            return
        url = self._url_edit.text().strip()
        if not url:
            return
        if not url.startswith("http"):
            url = "https://" + url
        self._link_btn.setEnabled(False)
        self._status_label.setText("Fetching preview...")
        self._og_worker = _OGFetchWorker(url)
        self._og_worker.done.connect(lambda og: self._on_og_done(url, og))
        self._og_worker.error.connect(self._on_og_error)
        self._og_worker.start()

    def _on_og_done(self, url: str, og: dict):
        caption, ok = QInputDialog.getText(self, "Caption", "Optional caption:")
        attach_link(
            self._book, self._chapter, self._verse,
            url, og, caption.strip() or None,
        )
        self._url_edit.clear()
        self._status_label.setText("Link added.")
        self._link_btn.setEnabled(True)
        self._refresh()
        self.changed.emit()

    def _on_og_error(self, err: str):
        # Save link without OG metadata
        url = self._url_edit.text().strip()
        attach_link(self._book, self._chapter, self._verse, url, {})
        self._url_edit.clear()
        self._status_label.setText(f"Saved (preview unavailable: {err[:60]})")
        self._link_btn.setEnabled(True)
        self._refresh()
        self.changed.emit()
