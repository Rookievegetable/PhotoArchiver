from PySide6.QtWidgets import QApplication, QMainWindow
import sys

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("PhotoArchiver")
window.resize(1200, 800)
window.show()

sys.exit(app.exec())
