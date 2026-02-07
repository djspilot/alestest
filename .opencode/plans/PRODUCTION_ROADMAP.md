# Manufacturing Pipeline - Production Readiness Roadmap

**Visual Roadmap for Company Stakeholders**

---

## 📊 Project Overview

| Parameter | Value |
|-----------|-------|
| **Team** | Solo Developer |
| **Timeline** | 4 Weeks (February 2026) |
| **Platform** | Windows Server/Workstation |
| **Purpose** | ERP Shadow Validation Tool |
| **Goal** | Compare pipeline results vs SpaceClaim standard |

---

## 🗓️ Week-by-Week Timeline

### **Week 1: 🪟 Windows Infrastructure**
**Goal**: Get it running on Windows reliably

**Tasks**:
- [ ] Update FreeCAD auto-detection for Windows paths
- [ ] Create Windows installation script
- [ ] Pin all dependency versions in requirements.txt
- [ ] Test clean install on Windows VM
- [ ] Set up basic pytest infrastructure (3 essential tests)

**Deliverable**: ✅ Pipeline runs on Windows without manual path edits

---

### **Week 2: 🔗 ERP Integration**
**Goal**: Robust ERP shadow validation tool

**Tasks**:
- [ ] Enhance batch folder processing with progress bar
- [ ] Add error tolerance (continue on single file failure)
- [ ] Support ERP file formats (Excel/XML)
- [ ] Implement deviation thresholds (±5% tolerance)
- [ ] Generate side-by-side comparison tables
- [ ] Export to Excel/CSV for ERP team review
- [ ] Build simple HTML validation dashboard

**Deliverable**: ✅ Can process ERP folder → generate deviation report

---

### **Week 3: 🛡️ Error Handling & Reliability**
**Goal**: Production-grade stability

**Tasks**:
- [ ] Add try/except wrappers around STEP file loading
- [ ] Add try/except for Excel parsing errors
- [ ] Add try/except for FreeCAD operations (unfold failures)
- [ ] Log errors to daily files (`logs/pipeline_YYYYMMDD.log`)
- [ ] Validate STEP files before processing (size, format)
- [ ] Check ERP file schema matches expected format
- [ ] Sanitize file paths (prevent traversal attacks)
- [ ] Set file size limits (e.g., max 500MB STEP files)
- [ ] Implement structured logging with timestamps
- [ ] Track metrics (files/hour, success rates, processing time)

**Deliverable**: ✅ Runs unattended on ERP data folders, logs issues, continues on errors

---

### **Week 4: 🚀 Polish & Deployment**
**Goal**: Ready for ERP team to use

**Tasks**:
- [ ] Write `DEPLOYMENT.md`: Windows installation steps
- [ ] Write `ERP_INTEGRATION.md`: How to use as shadow process
- [ ] Update CLI help text with examples
- [ ] Implement parallel batch processing (4-8 workers)
- [ ] Add result caching (avoid re-processing)
- [ ] Memory optimization for large files
- [ ] Test on sample ERP dataset (5-10 parts)
- [ ] Compare results with SpaceClaim manually
- [ ] Document any systematic deviations
- [ ] Fix critical discrepancies
- [ ] Create deployment checklist
- [ ] Package with all dependencies pinned
- [ ] Create Windows batch scripts (`.bat` files)
- [ ] Create sample config file
- [ ] Handover documentation for ERP team

**Deliverable**: ✅ Production-ready ERP shadow validation tool

---

## ✅ Scope: What We're Doing vs Skipping

### ❌ SKIP for Now (Time Constraints)
- Full test coverage (>80%) 
- CI/CD pipeline (GitHub Actions)
- API documentation (Sphinx/pdoc)
- Database storage layer
- Entry point unification (run.py, cli.py, main.py)
- Advanced performance optimization
- Multi-platform support (Linux/macOS)
- Complex refactoring of large files
- Complete code reorganization

### ✅ KEEP & Focus On
- **ERP comparison workflow** (CORE FEATURE)
- **Windows compatibility** (PLATFORM REQUIREMENT)
- **Error handling & logging** (STABILITY)
- **Batch processing** (SCALABILITY)
- **Deviation reporting** (BUSINESS VALUE)
- **Basic testing** (CONFIDENCE)
- **Dependency pinning** (RELIABILITY)
- **Input validation** (SECURITY)

---

## 📈 Target Metrics

| Metric | Target |
|--------|--------|
| Timeline | 4 Weeks |
| Windows Compatibility | 95%+ |
| Deviation Tolerance | ±5% |
| Operation Mode | 24/7 Unattended |
| Test Coverage | Core Windows paths (basic) |

---

## 🔧 Critical Windows-Specific Changes

### 1. FreeCAD Auto-Detection
Current code has hardcoded macOS paths:
```python
freecad_path: str = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
```

**Windows Implementation**:
```python
def find_freecad_windows():
    """Auto-detect FreeCAD on Windows."""
    possible_paths = [
        os.environ.get("FREECAD_PATH"),
        r"C:\Program Files\FreeCAD 1.0\bin",
        r"C:\Program Files (x86)\FreeCAD 1.0\bin",
        r"C:\Users\<user>\AppData\Local\Programs\FreeCAD\bin",
    ]
    for path in possible_paths:
        if path and os.path.exists(os.path.join(path, "python.exe")):
            return path
    raise RuntimeError("FreeCAD not found. Set FREECAD_PATH environment variable.")
```

### 2. Path Handling
- Use `pathlib.Path` everywhere (handles `/` vs `\` automatically)
- Avoid hardcoded Unix paths

### 3. ERP Deviation Logic
```python
def compare_with_tolerance(pipeline_val, erp_val, tolerance=0.05):
    """Compare values with ±5% tolerance."""
    if erp_val == 0:
        return pipeline_val == 0
    deviation = abs(pipeline_val - erp_val) / erp_val
    return deviation <= tolerance
```

---

## 📋 Success Criteria

**Minimum Viable Product (Week 4)**:
1. ✅ Runs on Windows without code changes
2. ✅ Processes ERP data folder automatically
3. ✅ Compares with SpaceClaim data (±5% tolerance)
4. ✅ Generates deviation report (Excel/CSV/HTML)
5. ✅ Continues processing on individual file errors
6. ✅ Logs all operations and errors
7. ✅ Can run unattended for hours

**Stretch Goals**:
- 8+ parallel workers for batch processing
- 95% match rate with SpaceClaim data
- Sub-30 second processing per file average

---

## 🚀 Getting Started

### Pre-Week 1 Checklist:
- [ ] Confirm FreeCAD installed on Windows target machine
- [ ] Identify ERP file formats (Excel columns, XML schema)
- [ ] Get sample dataset (5-10 STEP files with ERP data)
- [ ] Confirm deployment environment details (Windows Server version, Python version)
- [ ] Set up Windows development VM or machine
- [ ] Verify SpaceClaim reference data format

---

## 📞 Support & Questions

**Quick Questions for Stakeholders**:
1. Is FreeCAD already installed on the Windows server?
2. What ERP file formats are used? (Excel + XML combo?)
3. Will this run on local Windows machine or shared server?
4. How many STEP files per batch? (10? 100? 1000?)
5. What's the acceptance tolerance? (e.g., 90% of parts within 5% deviation?)

---

**Status**: 🚀 Ready to Begin Implementation  
**Last Updated**: February 2026  
**Next Review**: End of Week 1
