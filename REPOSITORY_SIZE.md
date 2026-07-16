# Repository Size Management

This document explains the BDA project's directory structure, expected sizes, and how to manage build artifacts.

## 📊 Expected Repository Sizes

### Source Code Only (Clean Clone)
**Size: ~5-10 MB**

This is the size after running `git clone` and includes:
- Python source code (Lambda functions, CDK stacks)
- JavaScript/React source code (UI components)
- Configuration templates
- Documentation

### With Build Artifacts (Development)
**Size: ~900 MB**

After running `./deploy.sh` or building locally, the repository includes:

| Directory/File | Size | Purpose | Tracked in Git? |
|----------------|------|---------|-----------------|
| `.venv/` | ~452 MB | Python dependencies (CDK, boto3, etc.) | ❌ No |
| `bda-cloudscape-ui/node_modules/` | ~446 MB | NPM packages (React, Cloudscape) | ❌ No |
| `bda-cloudscape-ui/dist/` | ~2.5 MB | Built frontend (HTML, JS, CSS) | ❌ No |
| `lambda_layers/*/python/` | ~33 MB | Lambda layer packages | ❌ No |
| `cdk.out/` | Varies | CDK CloudFormation templates | ❌ No |
| `.cdk.staging/` | Varies | CDK staging assets | ❌ No |
| Source code | ~5-10 MB | Actual project code | ✅ Yes |

## 🧹 Cleaning Up Build Artifacts

### Quick Cleanup
```bash
# Remove all build artifacts and dependencies
./scripts/cleanup.sh
```

This brings the repository back to ~5-10 MB by removing:
- Python virtual environment (`.venv/`)
- Node modules (`node_modules/`)
- Built frontend (`dist/`)
- CDK output (`cdk.out/`, `.cdk.staging/`)
- Lambda layers (built packages)
- Python cache files (`__pycache__`, `*.pyc`)
- Log files

### Manual Cleanup
```bash
# Remove specific items
rm -rf .venv                          # Python virtual environment (452 MB)
rm -rf bda-cloudscape-ui/node_modules # NPM packages (446 MB)
rm -rf bda-cloudscape-ui/dist         # Built frontend (2.5 MB)
rm -rf cdk.out .cdk.staging          # CDK artifacts
rm -rf lambda_layers/*/python         # Lambda layer packages
```

## 🔄 Restoring Build Environment

After cleanup, restore the build environment:

### Option 1: Full Deployment (Recommended)
```bash
./deploy.sh --profile YourProfile
```
This automatically:
- Creates Python virtual environment
- Installs Python dependencies
- Builds Lambda layers
- Installs NPM packages
- Builds frontend
- Deploys infrastructure

### Option 2: Manual Setup
```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Frontend dependencies
cd bda-cloudscape-ui
npm install
npm run build
cd ..

# 3. Deploy
./deploy.sh --profile YourProfile
```

## 🚀 Optimizing Development Workflow

### Use Fast Deployment Modes
Instead of full deployments that rebuild everything:

```bash
# Quick mode: Skip Docker images + UI rebuild (~10-15 min)
./deploy.sh --quick --profile YourProfile

# Config only: Just update runtime config (~5-8 min)
./deploy.sh --config-only --profile YourProfile

# Skip UI build: Deploy infrastructure + config.json only (~15-20 min)
./deploy.sh --skip-ui-build --profile YourProfile
```

See `./deploy.sh --help` for all options.

### Cache Optimization

**Docker Build Context:**
The `.dockerignore` file prevents large directories from being sent to Docker:
- `node_modules/` (446 MB)
- `.venv/` (452 MB)
- `cdk.out/` (varies)

This speeds up Docker builds from ~5-10 minutes to ~2-3 minutes.

**Docker Image Caching:**
The deployment script checks if Docker images already exist in ECR before rebuilding.
This saves 15-20 minutes on subsequent deployments.

## 📦 What Gets Committed to Git?

### ✅ Committed (Tracked)
- Python source code (`*.py`)
- JavaScript/React source code (`*.js`, `*.jsx`)
- CDK infrastructure definitions (`bda_stacks/`)
- Lambda function code (`Lambda/`)
- Configuration templates (`*.template`, `.env.template`)
- Requirements files (`requirements.txt`, `package.json`)
- Documentation (`*.md`)
- Scripts (`scripts/`)

### ❌ Not Committed (Ignored)
- Virtual environments (`.venv/`, `venv/`)
- Node modules (`node_modules/`)
- Build artifacts (`dist/`, `build/`)
- CDK output (`cdk.out/`, `.cdk.staging/`)
- Lambda layers (built packages)
- Environment files (`.env`, `config.json`)
- Log files (`*.log`)
- Cache files (`__pycache__/`, `*.pyc`)

## 🔍 Checking Repository Size

```bash
# Total project size
du -sh .

# Breakdown by directory
du -h -d 1 . | sort -rh | head -10

# Size without build artifacts (source code only)
du -sh --exclude=.venv --exclude=node_modules --exclude=dist --exclude=cdk.out .
```

## 🎯 Best Practices

1. **Regular Cleanup**: Run `./cleanup.sh --local-only` before committing large changes
2. **Use Fast Modes**: Use `--quick` or `--config-only` for development iterations
3. **Check .gitignore**: Ensure new build artifacts are ignored
4. **Monitor Size**: Check repository size before git operations
5. **Clean Clones**: Test with fresh clones periodically to ensure proper .gitignore coverage

## 📚 Related Documentation

- [deploy.sh --help](deploy.sh) - Deployment options and modes
- [cleanup.sh --help](cleanup.sh) - Cleanup options (AWS + local)
- [.gitignore](.gitignore) - Files excluded from Git
- [.dockerignore](.dockerignore) - Files excluded from Docker build context

## ❓ FAQ

**Q: Why is my repository 900 MB?**
A: This is normal with build artifacts. The actual source code is only ~5-10 MB. Run `./cleanup.sh --local-only` to remove build artifacts.

**Q: Can I reduce the size of node_modules?**
A: Modern JavaScript projects typically have large `node_modules`. The dependencies are necessary for the UI. They're excluded from Git and Docker contexts.

**Q: Should I commit the .env file?**
A: **NO!** The `.env` file contains secrets and AWS credentials. It's in `.gitignore` for security. Use `.env.template` for documentation.

**Q: Why do Docker builds take so long?**
A: Check that `.dockerignore` is properly configured. It should exclude `node_modules/`, `.venv/`, and other large directories from the build context.

**Q: Can I delete cdk.out safely?**
A: Yes! CDK recreates `cdk.out/` on every `cdk synth` or `cdk deploy`. It's safe to delete and is excluded from Git.

**Q: Why does cdk.out have thousands of files?**
A: CDK creates a synthesized CloudFormation template and asset manifest for each deployment. With multiple stacks and assets (Lambda layers, UI builds), this can grow to 5000+ files. This is normal and gets regenerated on each deployment.

**Q: cdk.out cleanup is slow, what can I do?**
A: For directories with 5000+ files, the cleanup script shows progress dots. You can:
1. Let it complete (may take 30-60 seconds)
2. Run `rm -rf cdk.out` manually in another terminal
3. Add `cdk.out` to your `.gitignore` (already done)

## 🐛 Troubleshooting

### Issue: Git operations are slow
**Solution:** Run `./cleanup.sh --local-only` to remove untracked build artifacts

### Issue: Docker build is slow
**Solution:** Check that `.dockerignore` includes `node_modules/` and `.venv/`

### Issue: "Disk space full" during deployment
**Solution:**
1. Run `./cleanup.sh --local-only`
2. Clear Docker images: `docker system prune -a`
3. Clear NPM cache: `npm cache clean --force`

### Issue: Repository size is larger than expected
**Solution:**
1. Check for untracked large files: `git status`
2. Verify .gitignore is working: `git check-ignore -v <file>`
3. Look for large files: `find . -type f -size +10M -not -path "./.git/*"`
