"""
FTIR Contamination Analyzer - the "Export report" sheet

Before the report is written, one sheet asks for what the report needs from a person:

    1  where        the folder (a new dated sub-folder is made in it)
    2  who          your name, shown as the person who analysed the samples (with your login
                    name, which is always recorded); remembered for next time
    3  sign         optional: the review decision (accept / accept with changes / re-measure),
                    a comment, and the statement "I have looked at the raw spectra ...".
                    A signed report shows who signed, when and what they decided, and the
                    signature is added to records/signatures.csv with the report's SHA-256.

Short names used in this file:
    t = theme colours

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .analysis import NO_MATCH, PROBABLE, WEAK
from .library_view import section, text_label
from .motion import Segmented
from .records import current_user, make_signoff
from .widgets import ElidedLabel, Theme, icon

DECISION_CHOICES = (("Not now", ""), ("Accept", "accept"), ("With changes", "accept with changes"),
                    ("Re-measure", "re-measure"))
STATEMENT = "I have looked at the raw spectra and agree with the conclusions, or I have noted my changes."


class ClickLabel(QLabel):
    """Words that wrap, and tick their box when clicked (a check box's own text cannot wrap)."""

    def __init__(self, text, on_click):
        super().__init__(text)
        self.setObjectName("Body")
        self.setWordWrap(True)
        self.setCursor(Qt.PointingHandCursor)
        self.on_click = on_click

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.on_click()


class ExportPanel(QWidget):
    """The content of the sheet: where the report goes, who made it, and the optional signature."""

    submitted = Signal(dict)          # {"folder": Path, "name": str, "signoff": dict or None}
    cancelled = Signal()

    def __init__(self, results, folder, name=""):
        super().__init__()
        t = Theme.t
        self.folder = Path(folder)
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 16, 22, 22)
        column.setSpacing(14)
        counts = {v: sum(r.verdict == v for r in results) for v in (PROBABLE, WEAK, NO_MATCH)}
        column.addWidget(text_label(
            f"{len(results)} spectr{'um' if len(results) == 1 else 'a'}: {counts[PROBABLE]} probable, "
            f"{counts[WEAK]} weak, {counts[NO_MATCH]} with no reliable match. The report comes as a PDF (A4 "
            "pages, to read, send or print), as a web page with interactive figures, and as an Excel table.",
            "Body2", wrap=True))

        # 1. where
        where_card, where_body = section("1   Where")
        row = QHBoxLayout()
        self.folder_label = ElidedLabel(str(self.folder), "Mono", Qt.ElideMiddle)
        choose = QPushButton(" Choose…")
        choose.setIcon(icon("folder-open", t["ink_2"]))
        choose.setCursor(Qt.PointingHandCursor)
        choose.clicked.connect(self.choose_folder)
        row.addWidget(self.folder_label, 1)
        row.addWidget(choose)
        where_body.addLayout(row)
        where_body.addWidget(text_label("A new folder with today's date and time is made in it.", "SectionHint",
                                        wrap=True))
        column.addWidget(where_card)

        # 2. who
        who_card, who_body = section("2   Who")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("your full name, e.g. Ali Obeidat")
        form.addWidget(text_label("Your name", "FactLabel"), 0, 0, Qt.AlignVCenter)
        form.addWidget(self.name, 0, 1)
        form.setColumnStretch(1, 1)
        who_body.addLayout(form)
        who_body.addWidget(text_label(f"Shown as the person who analysed the samples, with your login name "
                                      f"({current_user()}), which is always recorded.", "SectionHint", wrap=True))
        column.addWidget(who_card)

        # 3. sign
        sign_card, sign_body = section("3   Review and sign", "optional")
        self.decision = Segmented("", choices=DECISION_CHOICES)
        self.decision.changed.connect(lambda _: self._update())
        decision_row = QHBoxLayout()
        decision_row.addWidget(text_label("Decision", "FactLabel"))
        decision_row.addSpacing(8)
        decision_row.addWidget(self.decision)
        decision_row.addStretch()
        sign_body.addLayout(decision_row)
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Comment (needed for 'with changes' and 're-measure')")
        self.comment.textChanged.connect(lambda _: self._update())
        sign_body.addWidget(self.comment)
        self.statement = QCheckBox()                                       # the tick box, and its words beside
        self.statement.setCursor(Qt.PointingHandCursor)                    # it in a label that wraps
        self.statement.setAccessibleName(STATEMENT)
        self.statement.toggled.connect(lambda _: self._update())
        self.statement_text = ClickLabel(STATEMENT, self.statement.toggle)
        statement_row = QHBoxLayout()
        statement_row.addWidget(self.statement, 0, Qt.AlignTop)
        statement_row.addWidget(self.statement_text, 1)
        sign_body.addLayout(statement_row)
        sign_body.addWidget(text_label("A signed report shows who signed it, when, and the decision. The signature "
                                       "is added to records/signatures.csv with the SHA-256 of the report file. Not "
                                       "now: the report has fields to sign by hand.", "SectionHint", wrap=True))
        column.addWidget(sign_card)
        column.addStretch()

        # the footer (placed by the sheet under the scrolling content)
        self.footer = QFrame()
        self.footer.setObjectName("SheetHeader")
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(22, 12, 22, 14)
        self.problem = text_label("", "SectionHint", wrap=True)
        foot.addWidget(self.problem, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled.emit)
        self.export_button = QPushButton(" Export report")
        self.export_button.setObjectName("Primary")
        self.export_button.setIcon(icon("file-down", t["on_primary"]))
        self.export_button.clicked.connect(self._submit)
        for button in (cancel, self.export_button):
            button.setCursor(Qt.PointingHandCursor)
            foot.addWidget(button)
        self.name.textChanged.connect(lambda _: self._update())
        self._update()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the report", str(self.folder))
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        self.folder = Path(folder)
        self.folder_label.setText(str(self.folder))
        self._update()

    def problems(self):
        """What still stops the export (an empty list = ready)."""
        missing = []
        if not self.folder.is_dir():
            missing.append("a folder that exists")
        if self.decision.value():
            if not self.name.text().strip():
                missing.append("your name to sign with")
            if not self.statement.isChecked():
                missing.append("the statement ticked")
            if self.decision.value() != "accept" and not self.comment.text().strip():
                missing.append("a comment")
        return missing

    def _update(self):
        missing = self.problems()
        signing = bool(self.decision.value())
        self.export_button.setText(" Sign and export" if signing else " Export report")
        self.export_button.setEnabled(not missing)
        self.problem.setText(("Needs " + ", ".join(missing) + ".") if missing else
                             ("Signed as " + (self.name.text().strip() or current_user()) + "." if signing else
                              "Every export is added to the audit log."))
        for widget in (self.comment, self.statement, self.statement_text):
            widget.setEnabled(signing)

    def _submit(self):
        if self.problems():
            return
        name = self.name.text().strip()
        decision = self.decision.value()
        signoff = make_signoff(name, decision, self.comment.text()) if decision else None
        self.submitted.emit({"folder": self.folder, "name": name, "signoff": signoff})
