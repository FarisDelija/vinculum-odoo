# Git Repository Setup Guide for Odoo App Store

## 📋 Overview

To submit your module to the Odoo App Store, you need to:
1. Set up a Git repository with the correct structure
2. Grant Odoo access to read your repository
3. Format the repository URL correctly

---

## 🔧 Step 1: Repository Structure

### Requirements:
- **One folder per module** at the root of your repository
- Your module folder should be: `qr_code_odoo/`
- Branch name must match Odoo version: `18.0` (for Odoo 18.0)

### Example Structure:
```
your-repository/
├── qr_code_odoo/          ← Your module folder (at root)
│   ├── __manifest__.py
│   ├── models/
│   ├── views/
│   ├── controllers/
│   └── ...
├── README.md              ← Optional: Repository-level README
└── .gitignore
```

**⚠️ Important:** The module folder (`qr_code_odoo/`) must be directly at the root, not nested inside another folder.

---

## 🌿 Step 2: Create/Branch for Odoo 18.0

### Option A: Create a new branch (Recommended)

```bash
# Navigate to your repository
cd /path/to/your/repository

# Create and switch to branch for Odoo 18.0
git checkout -b 18.0

# Or if you want to base it on main/master:
git checkout main
git checkout -b 18.0
```

### Option B: Use existing branch

```bash
# Rename current branch to 18.0 if needed
git branch -m 18.0

# Or create 18.0 branch from current branch
git checkout -b 18.0
```

**Branch naming rules:**
- Use exactly `18.0` for Odoo 18.0 modules
- Use `17.0` for Odoo 17.0 modules
- Match the Odoo major.minor version

---

## 📤 Step 3: Commit and Push Your Module

```bash
# Make sure you're on the 18.0 branch
git checkout 18.0

# Add all your module files
git add qr_code_odoo/

# Commit your changes
git commit -m "Add Vinculum module v18.0.1.0.18 for Odoo App Store"

# Push to remote repository
git push origin 18.0

# If branch doesn't exist remotely yet:
git push -u origin 18.0
```

---

## 🔐 Step 4: Grant Repository Access to Odoo

Odoo needs **read-only access** to scan and publish your module.

### For GitHub:

1. **Go to your repository on GitHub**
   - Navigate to: `https://github.com/YOUR_USERNAME/YOUR_REPO`

2. **Go to Settings → Collaborators**
   - Click on your repository
   - Go to "Settings" tab
   - Click "Collaborators" in the left sidebar

3. **Add Odoo's GitHub user**
   - Click "Add people"
   - Search for: `online-odoo` (NOT `odoo-online`)
   - Select the user
   - Set permission to: **Read** (minimum required)
   - Click "Add online-odoo to this repository"

4. **Verify**
   - You should see `online-odoo` in the collaborators list with "Read" access

**Alternative: Make repository public** (if you're okay with code being public):
- Settings → Danger Zone → Change visibility → Make public
- No collaborator access needed for public repos

---

### For GitLab:

1. **Go to your repository on GitLab**
   - Navigate to your project

2. **Go to Project Settings → Members**
   - Click on your project
   - Go to "Settings" → "Members"

3. **Invite Odoo's GitLab user**
   - Click "Invite members"
   - Enter email: `apps@odoo.com`
   - Or username: `OdooApps`
   - Set role to: **Reporter** (read-only access)
   - Click "Invite"

4. **Verify**
   - Wait for them to accept (may need to contact them)
   - You'll see `OdooApps` in members list

---

### For Bitbucket:

1. **Get Odoo's public SSH key**
   - Contact `apps@odoo.com` to request their public SSH key

2. **Add SSH key**
   - Go to Repository Settings → Access keys
   - Add the public SSH key provided by Odoo

3. **Alternatively: Make repository public**
   - Settings → Repository details → Make repository public
   - No SSH key needed for public repos

---

## 🔗 Step 5: Format Repository URL

### Standard SSH URL Format:

```
ssh://git@github.com/YOUR_USERNAME/YOUR_REPO.git#18.0
```

### Breakdown:
- `ssh://` - Protocol (required, not HTTPS)
- `git@github.com` - Git server (use `git@gitlab.com` for GitLab, etc.)
- `YOUR_USERNAME/YOUR_REPO.git` - Repository path
- `#18.0` - Branch name (must match Odoo version)

### Examples:

**GitHub:**
```
ssh://git@github.com/farisdelija/vinculum-odoo.git#18.0
```

**GitLab:**
```
ssh://git@gitlab.com/farisdelija/vinculum-odoo.git#18.0
```

**Bitbucket:**
```
ssh://git@bitbucket.org/farisdelija/vinculum-odoo.git#18.0
```

**Custom Git Server (with port):**
```
ssh://git@git.example.com:2222/farisdelija/vinculum-odoo.git#18.0
```

---

## ✅ Step 6: Verify Setup

Before submitting, verify:

1. **Repository structure:**
   ```bash
   # Check that module is at root
   ls -la
   # Should show: qr_code_odoo/
   ```

2. **Branch exists:**
   ```bash
   git branch -a
   # Should show: * 18.0 (or remotes/origin/18.0)
   ```

3. **Files are committed:**
   ```bash
   git status
   # Should show: "nothing to commit, working tree clean"
   ```

4. **Access permissions:**
   - GitHub: Check Settings → Collaborators for `online-odoo`
   - GitLab: Check Members for `OdooApps`
   - Bitbucket: Confirm SSH key or public access

5. **Test SSH access** (if using SSH):
   ```bash
   # Test that SSH URL works
   git ls-remote ssh://git@github.com/YOUR_USERNAME/YOUR_REPO.git#18.0
   ```

---

## 📝 Step 7: Register in Odoo Apps Portal

1. **Log in to Odoo Apps Vendor Portal**
   - Go to: https://www.odoo.com/apps
   - Log in with your vendor account

2. **Navigate to: Submit your Apps & Themes**

3. **Register your Git repository**
   - Enter your repository URL in the format:
     ```
     ssh://git@github.com/YOUR_USERNAME/YOUR_REPO.git#18.0
     ```
   - Odoo will validate the URL format

4. **Wait for repository scan**
   - Odoo will scan your repository
   - It will detect modules in root folders
   - Your module should appear automatically

5. **Verify module appears**
   - Check that `qr_code_odoo` module is listed
   - Verify metadata (name, version, price) is correct
   - Check that icon and description load

---

## 🚨 Common Issues & Solutions

### Issue: "Repository access denied"
**Solution:**
- Verify collaborator/permissions are set correctly
- For GitHub: Check `online-odoo` has read access
- For GitLab: Verify `OdooApps` is added as Reporter
- Try making repo public temporarily to test

### Issue: "Module not found"
**Solution:**
- Ensure module folder is at repository root (not nested)
- Verify branch name matches (`18.0`)
- Check that files are committed and pushed

### Issue: "Invalid URL format"
**Solution:**
- Must use SSH URL (`ssh://git@...`), not HTTPS
- Include branch name: `#18.0`
- No trailing slashes

### Issue: "Wrong branch"
**Solution:**
- Branch name must exactly match Odoo version
- For Odoo 18.0: Use `18.0` (not `master`, `main`, or `v18.0`)
- Create branch if it doesn't exist

---

## 🔄 Updating Your Module

After initial submission:

1. **Make changes to your module**
2. **Commit changes:**
   ```bash
   git add qr_code_odoo/
   git commit -m "Update to version 18.0.1.0.19"
   git push origin 18.0
   ```
3. **Update version in `__manifest__.py`**
4. **Odoo will automatically detect updates** on next scan

---

## 📧 Need Help?

If you encounter issues:
- **Email Odoo Apps team**: apps@odoo.com
- **Include in your email:**
  - Repository URL
  - Branch name
  - Module name
  - Error message (if any)
  - Screenshot of issue

---

## ✅ Quick Checklist

Before submitting, ensure:

- [ ] Module folder (`qr_code_odoo/`) is at repository root
- [ ] Branch `18.0` exists and is pushed to remote
- [ ] All files are committed and pushed
- [ ] Repository access granted to Odoo (GitHub: `online-odoo`, GitLab: `OdooApps`)
- [ ] Repository URL is formatted correctly: `ssh://git@.../repo.git#18.0`
- [ ] Module version is updated in `__manifest__.py`
- [ ] Icon, cover image, and description are in place
- [ ] License file exists and is referenced correctly

---

**Ready to submit?** Head to the Odoo Apps Vendor Portal and register your repository!

