# Documentation Index

## 📚 Project Documentation Structure

This directory contains all project documentation organized by purpose and audience.

### 📂 Directory Structure

```
docs/
├── README.md                        # This file - documentation index
├── development/                     # Developer documentation
│   ├── PROJECT_HISTORY.md          # Project evolution and AI context
│   ├── DEVELOPMENT_LOG.md          # Development log with issues and fixes
│   ├── REFACTORING_CHECKLIST.md    # Refactoring progress tracking
│   ├── DEEP_VERIFICATION_PLAN.md   # Testing and verification methodology
│   └── CURSOR_RULES.md             # Development guidelines and standards
└── user/                           # User documentation (future)
    └── (user guides, tutorials)
```

### 🎯 Documentation by Audience

#### 👨‍💻 **For Developers**
- **[Project History](development/PROJECT_HISTORY.md)** - Evolution, architecture, and AI context for the project
- **[Development Guidelines](development/CURSOR_RULES.md)** - Comprehensive development standards and best practices
- **[Development Log](development/DEVELOPMENT_LOG.md)** - Detailed log of issues encountered and fixes applied during development
- **[Refactoring Checklist](development/REFACTORING_CHECKLIST.md)** - Complete comparison between original and refactored code
- **[Deep Verification Plan](development/DEEP_VERIFICATION_PLAN.md)** - Testing methodology and system verification results

#### 👥 **For Users**
- **[Main README](../README.md)** - Primary project documentation (in root directory)
- **User Documentation** - Coming soon in `user/` directory

#### ⚙️ **Configuration**
- **[.cursorrules](../.cursorrules)** - IDE configuration file (in root directory)

---

## 🗂️ Why This Structure?

### **Root Directory**
Files that should remain in the root for standard conventions:
- `README.md` - GitHub/GitLab standard for primary documentation
- `CURSOR_RULES.md` - Close to `.cursorrules` configuration file
- `.cursorrules` - IDE configuration file

### **docs/development/**
Technical documentation for developers:
- Issue tracking and resolution logs
- Code comparison and refactoring progress
- Testing and verification procedures
- Internal development guidelines

### **docs/user/**
User-facing documentation (future expansion):
- Installation guides
- Usage tutorials
- API documentation
- Troubleshooting guides

### **Benefits of This Organization**
1. **Clear Separation** - Developer vs user documentation
2. **Reduced Root Clutter** - Cleaner project root directory
3. **Better Navigation** - Logical grouping of related documents
4. **Scalability** - Easy to add new documentation categories
5. **Standard Compliance** - Follows common open-source practices

---

## 🔄 Quick Navigation

### Current Development Status
- [Latest Development Log Entry](development/DEVELOPMENT_LOG.md#log-entry-001---2025-01-21) - Template error fix
- [Refactoring Progress](development/REFACTORING_CHECKLIST.md#прогресс) - 100% complete
- [System Verification](development/DEEP_VERIFICATION_PLAN.md#итоговый-результат-глубокой-проверки) - All components verified

### Getting Started
- [Installation & Setup](../README.md#installation) - How to install and run the project
- [Basic Usage](../README.md#basic-usage) - Quick start guide
- [Server Management](../README.md#server-management) - Running the web interface

---

*This documentation structure follows industry best practices for open-source projects.* 