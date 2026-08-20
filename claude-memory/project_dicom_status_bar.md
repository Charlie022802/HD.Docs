---
name: project_dicom_status_bar
description: HD.DicomImageViewer status bar migration — moved ZoomFactor/PixelValue/Coordinate/DicomNumber/ViewIndex from MenuControl to StudyControl bottom strip
metadata: 
  node_type: memory
  type: project
  originSessionId: dc8af855-0b75-4ea2-84b4-e4b433b3f612
---

Status bar migration completed (2026-07-01).

**Why:** Labels were in MenuControlHorizontal/Vertical (global), but info is per-study-cell. Moved to StudyControl so multi-study layouts (2×2 etc.) each show their own image info independently.

**Architecture:**
- `StudyControl.InitStatusBar()` adds `panelStatusBar` (Dock=Bottom, 22px) programmatically; `panel1` (Dock=Fill, LayoutManager container) automatically shrinks — no Designer changes needed
- `StudyControl.UpdateStatusBar(ImageControlProperty)` updates the 5 labels via Invoke
- `MenuForm.timer1_Tick` tracks `hoveredStudy` (StudyControl) and calls `study.UpdateStatusBar(property)`
- UX: sticky (keeps last values, no clear on mouse-leave) — matches RadiAnt/Osirix convention

**Removed from MenuControl:** tableLayoutPanel1/2/3, labelZoomFactor, labelPixelValue, labelCoordinate, labelDicomNumber, labelViewIndex from both MenuControlHorizontal and MenuControlVertical (Designer + .cs + DoubleBuffering calls)

**How to apply:** If adding more per-image metadata display, add to StudyControl.UpdateStatusBar, not MenuControl.
