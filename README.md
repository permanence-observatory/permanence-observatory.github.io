# 🗺️ Slum News Map - Automated Daily Updates

An automatically-updating interactive map tracking news about informal settlements globally, powered by GDELT data.

**Live Map:** [https://permanence.github.io](https://permanence.github.io)

## 📋 Features

- **Daily automatic updates** via GitHub Actions
- **Interactive map** with 200+ global locations
- **Event filtering** (evictions, fires, violence, health, etc.)
- **Historical data** archived as dated CSV files
- **Powered by GDELT** - comprehensive global news coverage

---

## 🚀 Setup Instructions (First Time)

### Step 1: Create Your Repository

1. Go to GitHub: https://github.com
2. Click the **"+"** icon (top-right) → **"New repository"**
3. Repository name: `permanence.github.io` ⚠️ **EXACT NAME REQUIRED**
4. Description: `Automated daily map of news about informal settlements`
5. Select **Public** (required for free GitHub Pages)
6. ✅ Check **"Add a README file"**
7. Click **"Create repository"**

⚠️ **IMPORTANT:** The repository name MUST be exactly `permanence.github.io` (your username + `.github.io`) to get the root domain URL.

### Step 2: Upload Files to Repository

1. Click **"Add file"** → **"Upload files"**
2. Upload these files:
   - `gdelt_version_v21.py`
   - `.github/workflows/update-map.yml`
3. Click **"Commit changes"**

### Step 3: Create Archive Directory

1. In your repository, click **"Add file"** → **"Create new file"**
2. In the name field, type: `archive/.gitkeep`
3. Click **"Commit changes"**

This creates an `archive/` folder where dated CSV files will be stored.

### Step 4: Enable GitHub Pages

1. Go to repository **Settings** → **Pages** (left sidebar)
2. Under **"Source"**, select:
   - Branch: `main`
   - Folder: `/ (root)`
3. Click **"Save"**
4. Wait 1-2 minutes, then refresh the page
5. You'll see: **"Your site is live at https://permanence.github.io"**

### Step 5: Run First Update

1. Go to **Actions** tab in your repository
2. Click **"Update Slum News Map Daily"** (left sidebar)
3. Click **"Run workflow"** → **"Run workflow"** button
4. Wait 2-3 minutes for the workflow to complete
5. Visit your live map at: `https://YOUR-USERNAME.github.io/slum-news-map`

---

## ⚙️ How It Works

### Automatic Daily Updates

The map updates automatically **every day at midnight UTC** (00:00).

- **GitHub Actions** runs the Python script
- **New HTML map** replaces the old `index.html`
- **CSV data** is archived with today's date: `slum_news_data_YYYY-MM-DD.csv`
- Changes are automatically committed and published

### File Structure

```
slum-news-map/
├── .github/
│   └── workflows/
│       └── update-map.yml          # Automation workflow
├── archive/
│   ├── slum_news_data_2026-01-31.csv
│   ├── slum_news_data_2026-02-01.csv
│   └── ...                         # Daily CSV backups
├── gdelt_version_v21.py            # Main Python script
├── index.html                      # Published map (auto-generated)
└── README.md                       # This file
```

### Data Sources

- **GDELT Project**: Global Database of Events, Language, and Tone
- Covers 200+ slum locations across Africa, Asia, and Latin America
- Multilingual keyword detection
- Event categorization (evictions, fires, violence, health, etc.)

---

## 🔧 Customization

### Change Update Time

Edit `.github/workflows/update-map.yml`:

```yaml
schedule:
  - cron: '0 0 * * *'  # Daily at 00:00 UTC
```

Examples:
- `'0 6 * * *'` - Daily at 6:00 AM UTC
- `'0 */12 * * *'` - Every 12 hours
- `'0 9 * * 1'` - Weekly on Mondays at 9:00 AM UTC

See [crontab.guru](https://crontab.guru) for help with cron syntax.

### Modify Map Appearance

Edit `gdelt_version_v21.py`:
- **Line 1338**: Change brand name
- **Colors/styling**: Search for CSS sections in the HTML template
- **Locations**: Modify the `location_db` dictionary (lines 32-250)

After editing, commit changes to GitHub. The next scheduled run will use your updates.

---

## 📊 Accessing Historical Data

All daily CSV files are stored in the `archive/` folder:

```
archive/slum_news_data_2026-01-31.csv
archive/slum_news_data_2026-02-01.csv
...
```

To download:
1. Go to the `archive/` folder in your repository
2. Click on any CSV file
3. Click **"Download"** button

---

## 🐛 Troubleshooting

### Map not updating?

1. Check **Actions** tab for workflow errors
2. Look for red ❌ marks
3. Click on the failed workflow to see error details

### Common issues:

- **No articles found**: GDELT API may be temporarily down (retry later)
- **Permission denied**: Ensure Actions have write permissions:
  - Go to **Settings** → **Actions** → **General**
  - Under "Workflow permissions", select **"Read and write permissions"**
  - Click **"Save"**

### Manual trigger:

You can run the update manually anytime:
1. Go to **Actions** tab
2. Click **"Update Slum News Map Daily"**
3. Click **"Run workflow"** → **"Run workflow"**

---

## 📝 License & Credits

- **Code**: Feel free to use and modify
- **Data**: GDELT Project (open data)
- **Map tiles**: OpenStreetMap contributors
- **Created by**: permanence.dev

---

## 🤝 Contributing

To improve the map:
1. Fork this repository
2. Make your changes
3. Submit a pull request

Or open an issue for suggestions!

---

## 📧 Contact

Questions or issues? Open a GitHub issue or contact the maintainer.

**Last updated**: Automatically via GitHub Actions ⚡
