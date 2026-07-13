# PhotoArchiver UI Rules

Version: 1.0.0

Status: Stable

Last Updated: 2026-07-01

---

# 1. Purpose

This document defines the UI development standards for the PhotoArchiver project.

The project uses **PySide6** as the only approved GUI framework.

All UI code MUST comply with these rules.

---

# 2. UI Design Principles

The user interface should be:

* Simple
* Consistent
* Responsive
* Predictable
* Easy to maintain

The UI exists to present information and collect user input.

Business logic belongs outside the UI.

---

# 3. Approved Framework

Approved GUI framework:

* PySide6

UI files:

* .ui (Qt Designer)
* Python generated from .ui (optional)
* Custom QWidget subclasses

No additional GUI frameworks are allowed.

---

# 4. Presentation Layer Responsibilities

Presentation is responsible for:

* Windows
* Dialogs
* Widgets
* Menus
* Toolbars
* Status Bar
* User interaction
* Displaying progress
* Displaying errors

Presentation MUST NOT contain business logic.

---

# 5. Main Window

## UI-001

The application entry window MUST be:

```text
MainWindow
```

Responsibilities:

* Create UI
* Connect signals
* Initialize controllers
* Display application state

---

## UI-002

MainWindow MUST NOT:

* execute SQL
* scan folders
* process images
* recognize faces
* read Excel
* perform archive generation

---

# 6. Dialogs

Dialogs SHOULD be lightweight.

Examples:

* ImportDialog
* ExportDialog
* SettingsDialog
* AboutDialog

Dialogs return user choices.

Business processing belongs to Application Services.

---

# 7. Widgets

Custom widgets SHOULD represent reusable UI components.

Examples:

* PersonCard
* PhotoPreview
* FolderTree
* ProgressPanel
* LogViewer

Widgets MUST NOT access repositories.

---

# 8. Controllers

Controllers belong in:

```text
presentation/controllers/
```

Responsibilities:

* Receive UI events
* Validate input
* Invoke Application Services
* Update views

Controllers MUST NOT contain business rules.

---

# 9. View Models

When view state becomes complex, use View Models.

Responsibilities:

* Format display data
* Store temporary UI state
* Adapt domain objects for presentation

View Models MUST NOT execute business logic.

---

# 10. Signals and Slots

Qt Signals SHOULD be used for:

* Button clicks
* Worker progress
* Completion notifications
* Error notifications
* UI refresh

Signals SHOULD replace direct widget-to-widget communication.

---

# 11. Long-running Tasks

Long-running operations MUST execute in Workers.

Examples:

* Scan folders
* Face recognition
* Import Excel
* Export reports
* Generate thumbnails

UI MUST remain responsive.

---

# 12. UI Updates

Only the UI thread may update widgets.

Workers MUST communicate through Signals.

Wrong:

```python
progress_bar.setValue(...)
```

inside Worker code.

Correct:

```text
Worker
↓

Signal

↓

Controller

↓

UI
```

---

# 13. Status Feedback

The UI SHOULD always provide feedback for long-running operations.

Approved methods:

* Progress Bar
* Status Bar
* Busy Indicator
* Spinner
* Toast Notification

The user should never wonder whether the application is still working.

---

# 14. Error Presentation

Errors SHOULD be presented clearly.

Provide:

* Human-readable message
* Suggested action (when appropriate)

Avoid exposing raw stack traces to users.

Detailed exceptions should be written to logs.

---

# 15. Logging Display

The UI MAY include a log viewer.

The log viewer is read-only.

Users MUST NOT edit application logs.

---

# 16. Theme Management

Themes belong in:

```text
config/themes/
```

UI styles belong in:

```text
resources/styles/
```

Hard-coded styles inside widgets should be avoided.

---

# 17. Icons

Icons belong in:

```text
resources/icons/
```

Do not embed binary icon data in source code.

---

# 18. Images

Application images belong in:

```text
resources/images/
```

User-imported images belong in:

```text
data/imports/
```

Never mix application resources with user data.

---

# 19. Fonts

Fonts belong in:

```text
resources/fonts/
```

Use embedded fonts only when necessary.

---

# 20. Window Layout

The main window SHOULD follow a consistent layout.

Recommended structure:

```text
+------------------------------------------------+
| Menu Bar                                       |
+------------------------------------------------+
| Toolbar                                        |
+------------------------------------------------+
| Navigation | Workspace | Information Panel     |
|            |           |                       |
+------------------------------------------------+
| Status Bar                                     |
+------------------------------------------------+
```

---

# 21. Progress Display

Batch operations SHOULD display:

* Current task
* Progress percentage
* Processed items
* Remaining items (if known)
* Estimated time (optional)

---

# 22. File Selection

All file and directory selection MUST use Qt dialogs.

Examples:

* QFileDialog.getOpenFileName()
* QFileDialog.getExistingDirectory()

Never require users to manually enter file paths.

---

# 23. User Settings

Application settings SHOULD be managed centrally.

Examples:

* Theme
* Language
* Default import path
* Default export path
* Window geometry

Settings MUST NOT be scattered across widgets.

---

# 24. Internationalization

All user-visible text SHOULD be prepared for translation.

Avoid hard-coded strings throughout the codebase.

---

# 25. Accessibility

The UI SHOULD support:

* Keyboard navigation
* Focus order
* High DPI displays
* Screen scaling

Text and icons should remain readable at different resolutions.

---

# 26. Naming Convention

Recommended names:

```text
MainWindow
ImportDialog
ExportDialog
SettingsDialog

FolderTreeWidget
PhotoGridWidget
PreviewWidget
ProgressWidget
LogViewerWidget
```

Names should clearly describe responsibilities.

---

# 27. Project-specific UI Flow

The recommended workflow is:

```text
Import Excel/TXT

↓

Select Photo Directory

↓

Build Folder Structure

↓

Scan Photos

↓

Face Recognition

↓

Match Results

↓

Review Results

↓

Archive

↓

Export Report
```

The UI should guide users through this workflow in a logical order.

---

# 28. Review Checklist

Before merging UI code verify:

* [ ] UI contains no business logic
* [ ] Uses Application Services
* [ ] Long tasks use Workers
* [ ] Signals used correctly
* [ ] UI updated only on main thread
* [ ] No direct SQL access
* [ ] No OpenCV calls
* [ ] No InsightFace calls
* [ ] Resources loaded from correct directories
* [ ] Logging handled properly
* [ ] User feedback implemented
* [ ] Consistent naming

---

# 29. Summary

The PhotoArchiver UI layer is responsible only for presentation.

It should remain lightweight, responsive, and independent of business logic.

All business workflows must be coordinated through the Application layer, while long-running operations execute in Workers.

Following these rules ensures a maintainable, scalable, and user-friendly desktop application.

---

End of Document
