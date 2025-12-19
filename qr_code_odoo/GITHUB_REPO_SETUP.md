# GitHub Repository Setup for Odoo App Store

## 📝 Repository Creation Form - Recommended Settings

### Owner*
- ✅ **FarisDelija** (already selected - correct)

### Repository name*
**Recommended:** `vinculum-odoo` or `qr-code-odoo-module`

**Tips:**
- Use lowercase letters and hyphens
- Keep it short and memorable
- Don't use spaces or special characters
- Examples:
  - ✅ `vinculum-odoo`
  - ✅ `vinculum-app-store`
  - ✅ `qr-code-odoo`
  - ❌ `Vinculum Odoo` (spaces)
  - ❌ `vinculum_odoo` (underscores not ideal)

### Description
**Recommended:** 
```
Digital business cards, lead capture & analytics for Odoo. Standalone module for self-hosted Odoo instances.
```

**Or shorter:**
```
Vinculum - Digital business cards & lead capture module for Odoo 18.0
```

### Choose visibility*
**Important decision:**

#### Option 1: **Public** ✅ (Recommended for App Store)
- ✅ Easier setup (no collaborator access needed)
- ✅ Odoo can access directly
- ✅ Transparent (users can see code before buying)
- ⚠️ Code is publicly visible

#### Option 2: **Private** 
- ✅ Code is hidden
- ⚠️ Must add `online-odoo` as collaborator
- ⚠️ Extra step for setup

**For App Store submission, Public is recommended** - it's simpler and Odoo requires code access anyway.

### Add README
**Recommendation:** ✅ **ON**

- Creates a README.md file automatically
- You can edit it later with your module details
- Good practice to have one
- Helpful for repository visitors

### Add .gitignore
**Recommendation:** ✅ **Python**

- Select "Python" from dropdown
- Will ignore `__pycache__/`, `*.pyc`, etc.
- Prevents committing unnecessary files

### Add license
**Recommendation:** ✅ **None** (Leave as "No license")

**Why?**
- Your module already has `LICENSE.txt` with OPL-1
- GitHub's license selector doesn't include OPL-1
- You'll manage license through your module's LICENSE.txt file

---

## ✅ Recommended Configuration Summary

```
Owner: FarisDelija
Repository name: vinculum-odoo
Description: Digital business cards, lead capture & analytics for Odoo. Standalone module for self-hosted Odoo instances.
Visibility: Public
Add README: ON
Add .gitignore: Python
Add license: No license
```

---

## 🚀 After Creating Repository

### Step 1: Upload Your Module

You have two options:

#### Option A: Using Git (Recommended)
```bash
# Navigate to your local module directory
cd "c:\Program Files\Odoo 18.0e.20251114\server\odoo\addons\qr_code_odoo"

# Initialize git (if not already)
git init

# Add remote repository
git remote add origin https://github.com/FarisDelija/vinculum-odoo.git

# Create branch for Odoo 18.0
git checkout -b 18.0

# Add all files
git add .

# Commit
git commit -m "Initial commit: Vinculum module v18.0.1.0.18"

# Push to GitHub
git push -u origin 18.0
```

#### Option B: Using GitHub Web Interface
1. After creating repo, click "uploading an existing file"
2. Drag and drop your entire `qr_code_odoo` folder
3. Commit directly to `18.0` branch (or create it first)

**⚠️ Important:** Make sure your module folder structure in the repo is:
```
vinculum-odoo/
└── qr_code_odoo/          ← Your module folder
    ├── __manifest__.py
    ├── models/
    ├── views/
    └── ...
```

### Step 2: Verify Structure

After uploading, your repository should look like:
```
https://github.com/FarisDelija/vinculum-odoo/
├── qr_code_odoo/
│   ├── __manifest__.py
│   ├── models/
│   ├── views/
│   ├── controllers/
│   └── ...
├── README.md
└── .gitignore
```

### Step 3: Set Up Branch (if not done)

```bash
# Create and switch to 18.0 branch
git checkout -b 18.0

# Push branch
git push -u origin 18.0
```

### Step 4: Get Repository URL

Your repository URL for Odoo App Store will be:
```
ssh://git@github.com/FarisDelija/vinculum-odoo.git#18.0
```

**Or if using HTTPS (for initial setup):**
```
https://github.com/FarisDelija/vinculum-odoo.git
```

---

## 🔐 Access Setup (if Repository is Private)

If you chose **Private** repository:

1. Go to your repository on GitHub
2. Click **Settings** (top right)
3. Click **Collaborators** (left sidebar)
4. Click **Add people**
5. Search for: `online-odoo`
6. Select user and set permission to **Read**
7. Click **Add online-odoo to this repository**

---

## ✅ Final Checklist

Before submitting to Odoo App Store:

- [ ] Repository is created
- [ ] Module folder (`qr_code_odoo/`) is uploaded
- [ ] Branch `18.0` exists
- [ ] All files are committed and pushed
- [ ] Repository is accessible (Public OR `online-odoo` has access)
- [ ] Repository URL is ready: `ssh://git@github.com/FarisDelija/REPO_NAME.git#18.0`

---

## 📧 Next Steps

1. **Create the repository** with recommended settings above
2. **Upload your module** to the repository
3. **Create branch `18.0`** and push your code
4. **Verify structure** - module folder should be at root
5. **Submit to Odoo App Store** using the repository URL

---

**Need help?** Check `GIT_SETUP_GUIDE.md` for detailed instructions!

