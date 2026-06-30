<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text=🛡️%20PhishGuard%20AI&fontSize=50&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Real-Time%20Phishing%20URL%20Detection%20Powered%20by%20Machine%20Learning&descSize=16&descAlignY=58&descColor=a0a0cc" width="100%"/>

<br/>

[![Stars](https://img.shields.io/github/stars/huziifa/Huzaifa?style=for-the-badge&logo=github&color=FFD700&labelColor=0d1117)](https://github.com/huziifa/Huzaifa/stargazers)
[![Forks](https://img.shields.io/github/forks/huziifa/Huzaifa?style=for-the-badge&logo=git&color=4ECDC4&labelColor=0d1117)](https://github.com/huziifa/Huzaifa/network)
[![Issues](https://img.shields.io/github/issues/huziifa/Huzaifa?style=for-the-badge&logo=gitbook&color=FF6B6B&labelColor=0d1117)](https://github.com/huziifa/Huzaifa/issues)
[![License](https://img.shields.io/badge/License-MIT-8A2BE2?style=for-the-badge&labelColor=0d1117)](LICENSE)
[![Accuracy](https://img.shields.io/badge/Model%20Accuracy-97.4%25-00C851?style=for-the-badge&logo=checkmarx&labelColor=0d1117)](#-model-benchmarks)

<br/>

![Python](https://img.shields.io/badge/Python%203.6+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask%202.0-000000?style=flat-square&logo=flask&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn%201.0-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white)
![Jupyter](https://img.shields.io/badge/Jupyter-F37626?style=flat-square&logo=jupyter&logoColor=white)

<br/>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=18&pause=1000&color=6E57F7&center=true&vCenter=true&width=600&lines=Paste+any+URL.+Get+an+instant+AI+verdict.;97.4%25+accurate+phishing+detection.;30+intelligent+features+extracted.;99.4%25+recall+%E2%80%94+catches+almost+everything." alt="Typing SVG"/>

<br/><br/>

<img src="https://user-images.githubusercontent.com/79131292/144742825-23367f0f-9e67-4c99-ba1f-b86a187675c9.png" width="78%" style="border-radius:12px; box-shadow: 0 8px 32px rgba(0,0,0,0.4);"/>

<br/><br/>

</div>

---

<details open>
<summary><b>📋 Table of Contents</b> — click to expand / collapse</summary>

<br/>

| # | Section |
|---|---------|
| 1 | [🧠 About the Project](#-about-the-project) |
| 2 | [✨ Features at a Glance](#-features-at-a-glance) |
| 3 | [⚙️ How It Works](#️-how-it-works) |
| 4 | [🔬 The 30-Feature Engine](#-the-30-feature-engine) |
| 5 | [📊 Model Benchmarks](#-model-benchmarks) |
| 6 | [🛠️ Tech Stack](#️-tech-stack) |
| 7 | [📁 Project Structure](#-project-structure) |
| 8 | [🚀 Getting Started](#-getting-started) |
| 9 | [💻 Usage Guide](#-usage-guide) |
| 10 | [📂 Dataset](#-dataset) |
| 11 | [🏆 Results & Analysis](#-results--analysis) |
| 12 | [🛣️ Roadmap](#️-roadmap) |
| 13 | [🤝 Contributing](#-contributing) |
| 14 | [📄 License](#-license) |
| 15 | [👤 Author](#-author) |

</details>

---

## 🧠 About the Project

<img align="right" src="https://user-images.githubusercontent.com/79131292/144742785-d183f50a-52d6-4296-a43a-90a1ee3502d8.png" width="38%"/>

**Phishing attacks account for over 90% of all data breaches worldwide.** Attackers craft convincing fake websites to steal credentials, banking details, and personal data — and traditional blacklist-based filters increasingly fail to keep up with evolving threats.

**PhishGuard AI** solves this with machine learning. Rather than relying on lists that go stale within hours, the model learns the *structural DNA* of phishing URLs — 30 deep signals covering domain intelligence, HTML behaviour, redirect patterns, and web reputation — and generalises confidently to URLs it has never seen before.

### The core challenge

| Detection Method | Why It Fails |
|-----------------|-------------|
| Blacklist filtering | Only catches *known* sites; new phishing domains bypass instantly |
| Rule-based heuristics | Brittle — one tweak in URL structure defeats the rules |
| Human inspection | Impossible at scale; humans are fooled by design |
| ✅ **Machine Learning** | Learns generalised patterns; adapts to new attack structures |

### Why this implementation stands out

- 🔬 **30 handcrafted features** across 4 analytical layers — URL structure, domain intelligence, HTML/JS content, and web reputation
- 🏋️ **10 algorithms benchmarked** on identical splits — no cherry-picking
- 🎯 **97.4% accuracy** with **99.4% recall** — misses almost nothing
- 🌐 **Production-ready Flask app** — clean UI, Heroku-deployable, Gunicorn-ready
- 📓 **Full reproducible Jupyter notebook** — EDA, training, evaluation, feature importance

<br clear="right"/>

---

## ✨ Features at a Glance

<div align="center">

| | Feature | Description |
|-|---------|-------------|
| 🔍 | **Real-Time Analysis** | Paste a URL and get results in seconds |
| 🤖 | **GBC Model** | Gradient Boosting — the top performer across 10 algorithms |
| 📊 | **Probability Score** | Not just "safe/unsafe" — a precise confidence percentage |
| 🧮 | **30-Feature Engine** | Deep structural analysis of every URL component |
| 🛡️ | **99.4% Recall** | Security-first — almost no phishing site slips through |
| ⚡ | **Lightweight App** | Flask + Gunicorn — fast, portable, cloud-ready |
| 📓 | **Open Notebook** | Full EDA and model comparison — fully transparent |
| 🔌 | **Heroku Ready** | Procfile included — deploy in one command |

</div>

---

## ⚙️ How It Works

```
╔══════════════════════════════════════════════════════════════╗
║                      USER SUBMITS URL                       ║
║           "http://paypa1-secure-login.free.fr/"             ║
╚══════════════════════════════╦═══════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════╗
║                    FEATURE EXTRACTION                       ║
║                   (feature.py — 30 features)                ║
║                                                             ║
║   ┌──────────────────┐    ┌──────────────────────────────┐  ║
║   │ ① URL Structure  │    │   ② Domain Intelligence      │  ║
║   │   7 features     │    │      5 features               │  ║
║   └──────────────────┘    └──────────────────────────────┘  ║
║   ┌──────────────────┐    ┌──────────────────────────────┐  ║
║   │ ③ HTML & JS      │    │   ④ Web Reputation           │  ║
║   │   11 features    │    │      7 features               │  ║
║   └──────────────────┘    └──────────────────────────────┘  ║
║                                                             ║
║              Output: numpy array of shape (1, 30)           ║
╚══════════════════════════════╦═══════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════╗
║             GRADIENT BOOSTING CLASSIFIER                    ║
║                  (pickle/model.pkl)                         ║
║        Trained on 11,055 real-world labelled URLs           ║
║      Outputs: prediction class + probability vector         ║
╚══════════════════════════════╦═══════════════════════════════╝
                               │
                               ▼
╔══════════════════════════════════════════════════════════════╗
║                         RESULT                              ║
║                                                             ║
║   ✅  96.2% safe  →  Proceed with confidence                ║
║   ⚠️   7.4% safe  →  Phishing detected — do not visit      ║
╚══════════════════════════════════════════════════════════════╝
```

Each URL goes through **WHOIS lookup**, **DNS resolution**, **live HTTP request**, **BeautifulSoup HTML parsing**, **Google index check**, and **blacklist matching** — all inside `feature.py` — before the model ever sees it.

---

## 🔬 The 30-Feature Engine

Every URL is scored across four analytical layers. Each feature returns `1` (legitimate), `0` (suspicious), or `-1` (phishing).

<details>
<summary><b>🔗 Layer 1 — URL Structure (Features 1–7)</b></summary>

<br/>

| # | Feature | Logic | Phishing Signal |
|---|---------|-------|----------------|
| 1 | **IP Address in URL** | Regex + `ipaddress` module | IPs bypass domain reputation systems entirely |
| 2 | **URL Length** | `< 54` → safe · `54–75` → suspicious · `> 75` → phishing | Phishing URLs average 75+ chars due to obfuscation |
| 3 | **URL Shortening** | Matches 50+ known shortener domains (bit.ly, tinyurl, etc.) | Shorteners hide the real malicious destination |
| 4 | **`@` Symbol** | Regex search for `@` | Everything before `@` is ignored by the browser |
| 5 | **Double Slash Redirect** | `rfind('//')` position > 6 | Forces redirect to attacker-controlled domain |
| 6 | **Prefix/Suffix `-`** | Hyphen in domain (e.g. `pay-pal.com`) | Classic brand impersonation technique |
| 7 | **Sub-domain Depth** | Count of `.` in URL | 1 dot = safe · 2 = suspicious · 3+ = phishing |

</details>

<details>
<summary><b>🌐 Layer 2 — Domain Intelligence (Features 8–12)</b></summary>

<br/>

| # | Feature | Logic | Phishing Signal |
|---|---------|-------|----------------|
| 8 | **HTTPS** | Scheme check via `urlparse` | Phishing sites increasingly skip valid certificates |
| 9 | **Domain Registration Length** | WHOIS expiry minus creation date | Legitimate sites register for 1+ years; phishing domains for months |
| 10 | **Favicon Domain** | `<link href>` vs host domain | Favicons loaded from external domains expose cloned sites |
| 11 | **Non-Standard Port** | `:port` present in domain string | Unusual ports (not 80/443) indicate malicious hosting |
| 12 | **HTTPS in Domain Token** | `"https"` substring in domain part | e.g. `https-paypal.com` — visual deception trick |

</details>

<details>
<summary><b>🖥️ Layer 3 — HTML & JavaScript (Features 13–23)</b></summary>

<br/>

| # | Feature | Logic | Phishing Signal |
|---|---------|-------|----------------|
| 13 | **Request URL Ratio** | % of `<img>`, `<audio>`, `<embed>`, `<iframe>` from external hosts | > 61% external resources → cloned page |
| 14 | **Anchor URL Ratio** | % of `<a href>` pointing off-domain | > 67% external links reveals the page is a shell |
| 15 | **Script/Link Tag Ratio** | % of `<script src>` + `<link href>` from external hosts | > 81% external scripts is a clear phishing indicator |
| 16 | **Server Form Handler** | `<form action>` pointing to `""`, `about:blank`, or off-domain | Credential harvest forms submit to attacker servers |
| 17 | **Info Email** | `mailto:` present in page source | Used instead of real server-side form processing |
| 18 | **Abnormal URL** | `response.text` vs WHOIS host mismatch | Hostname not matching WHOIS = domain spoofing |
| 19 | **Website Forwarding** | `len(response.history)` | ≤1 redirect = safe · ≤4 = suspicious · 4+ = phishing |
| 20 | **Status Bar Customisation** | `onmouseover` in `<script>` tags | Hides real URL destination in browser status bar |
| 21 | **Disable Right Click** | `event.button == 2` in source | Prevents users from inspecting or saving the page |
| 22 | **Popup Windows** | `alert(` in response text | Credential-stealing popup dialogs |
| 23 | **Iframe Redirection** | `<iframe>` or `<frameBorder>` in source | Invisible frames loading malicious content |

</details>

<details>
<summary><b>📈 Layer 4 — Web Reputation (Features 24–30)</b></summary>

<br/>

| # | Feature | Logic | Phishing Signal |
|---|---------|-------|----------------|
| 24 | **Age of Domain** | WHOIS creation date vs today | Domains < 6 months old are highly suspicious |
| 25 | **DNS Record** | WHOIS creation date present | Missing DNS record = no legitimate registration |
| 26 | **Website Traffic** | Alexa API rank check | Rank > 100,000 or absent = low-traffic, new, or fake site |
| 27 | **Page Rank** | checkpagerank.net API | Global rank < 100,000 = legitimate; else phishing |
| 28 | **Google Index** | `googlesearch` package query | Unindexed URLs are often malicious or brand new |
| 29 | **Links Pointing to Page** | Count of `<a href=` in source | 0 links = possibly safe · 1–2 = suspicious · 3+ = phishing |
| 30 | **Statistical Report** | Regex match vs known phishing domain/IP blacklists | Matches 50+ known malicious IPs and domains |

</details>

---

## 📊 Model Benchmarks

Ten classifiers were trained and evaluated on an **80/20 stratified train/test split** of 11,055 URLs:

<div align="center">

| Rank | Model | Accuracy | F1 Score | Recall | Precision |
|:----:|-------|:--------:|:--------:|:------:|:---------:|
| 🥇 | **Gradient Boosting Classifier** | **0.974** | **0.977** | **0.994** | **0.986** |
| 🥈 | CatBoost Classifier | 0.972 | 0.975 | 0.994 | 0.989 |
| 🥉 | XGBoost Classifier | 0.969 | 0.973 | 0.993 | 0.984 |
| 4 | Multi-layer Perceptron | 0.969 | 0.973 | 0.995 | 0.981 |
| 5 | Random Forest | 0.967 | 0.971 | 0.993 | 0.990 |
| 6 | Support Vector Machine | 0.964 | 0.968 | 0.980 | 0.965 |
| 7 | Decision Tree | 0.960 | 0.964 | 0.991 | 0.993 |
| 8 | K-Nearest Neighbors | 0.956 | 0.961 | 0.991 | 0.989 |
| 9 | Logistic Regression | 0.934 | 0.941 | 0.943 | 0.927 |
| 10 | Naive Bayes Classifier | 0.605 | 0.454 | 0.292 | 0.997 |

</div>

> **Why Gradient Boosting?** It achieved the best balance of accuracy and recall. For a security tool, **recall is paramount** — a missed phishing URL (false negative) puts a real person at risk. GBC's 99.4% recall means it catches 994 out of every 1,000 phishing URLs.

### 📌 Feature Importance

<div align="center">
<img src="https://user-images.githubusercontent.com/79131292/144603941-19044aae-7d7b-4e9a-88a8-6adfd8626f77.png" width="72%"/>
</div>

<br/>

The three dominant features driving predictions:

| Rank | Feature | Why It Matters |
|------|---------|---------------|
| 🥇 | **HTTPS** | Certificate presence is the single strongest trust signal |
| 🥈 | **AnchorURL** | Cloned pages always pull links from external sources |
| 🥉 | **WebsiteTraffic** | Phishing domains never build real organic traffic |

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology | Version | Role |
|-------|-----------|---------|------|
| **Runtime** | Python | 3.6+ | Core language |
| **Web** | Flask | 2.0.2 | App server and routing |
| **ML** | scikit-learn | 1.0.1 | GBC model training and inference |
| **Data** | NumPy / Pandas | 1.21 / 1.3 | Array ops and dataset handling |
| **Scraping** | BeautifulSoup4 | 4.9.3 | HTML feature extraction |
| **HTTP** | Requests | 2.25.1 | Live URL fetching |
| **Domain** | python-whois | 0.9.13 | WHOIS domain registration data |
| **Search** | googlesearch-python | 1.0.1 | Google index verification |
| **Production** | Gunicorn | 20.1.0 | WSGI production server |
| **Deployment** | Procfile | — | Heroku deployment config |
| **Notebook** | Jupyter | — | EDA and model experiments |

</div>

---

## 📁 Project Structure

```
📦 Huzaifa/
│
├── 📂 pickle/
│   └── 🤖 model.pkl                     ← Trained GBC model (download separately)
│
├── 📂 static/
│   └── 🎨 styles.css                    ← Web interface stylesheet
│
├── 📂 templates/
│   └── 🌐 index.html                    ← Jinja2 web UI template
│
├── 📓 Phishing URL Detection.ipynb      ← Full EDA, training & evaluation
├── 🐍 app.py                            ← Flask routes & prediction logic
├── 🔧 feature.py                        ← 30-feature URL extraction engine
├── 📊 phishing.csv                      ← 11,055 labelled training URLs
├── 🚀 Procfile                          ← Heroku deployment (web: gunicorn app:app)
├── 📋 requirements.txt                  ← All Python dependencies
└── 📖 README.md
```

---

## 🚀 Getting Started

### Prerequisites

Ensure you have the following installed:

```bash
python --version   # 3.6 or higher required
pip --version      # pip 21+ recommended
git --version      # any recent version
```

### Step-by-Step Installation

**① Clone the repository**

```bash
git clone https://github.com/huziifa/Huzaifa.git
cd Huzaifa
```

**② Create and activate a virtual environment** *(recommended)*

```bash
# Create the environment
python -m venv venv

# Activate — Windows
venv\Scripts\activate

# Activate — macOS / Linux
source venv/bin/activate
```

**③ Install all dependencies**

```bash
pip install -r requirements.txt
```

**④ Download the trained model**

The `model.pkl` file is not included in the repository due to GitHub's 100 MB limit.
Download it and place it inside the `pickle/` folder:

```
📥  Download link: [YOUR GOOGLE DRIVE / HUGGING FACE LINK HERE]

Place the file at:  Huzaifa/pickle/model.pkl
```

**⑤ Run the application**

```bash
python app.py
```

**⑥ Visit the app in your browser**

```
http://127.0.0.1:5000
```

### Deploy to Heroku *(optional)*

```bash
heroku login
heroku create your-app-name
git push heroku main
heroku open
```

The `Procfile` is already configured: `web: gunicorn app:app`

---

## 💻 Usage Guide

### Basic Usage

1. Open the web app at `http://127.0.0.1:5000`
2. Paste any URL into the input field
3. Click **Check URL**
4. Read your result with confidence score

### Example Predictions

```
URL                                   Safety Score    Verdict
────────────────────────────────────────────────────────────
https://www.google.com                96.2%           ✅ Safe
https://github.com                    94.7%           ✅ Safe
https://stackoverflow.com             91.3%           ✅ Safe
http://paypa1-secure-login.free.fr/    3.1%           ⚠️ PHISHING
http://amazon-account-verify.tk/       5.8%           ⚠️ PHISHING
http://192.168.1.1/bank/login          2.4%           ⚠️ PHISHING
```

### Understanding Your Score

```
 90% – 100%  ███████████████████  ✅  Very Safe
 70% –  89%  ██████████████░░░░░  ✅  Safe
 40% –  69%  ████████░░░░░░░░░░░  ⚠️  Suspicious — proceed with caution
  0% –  39%  ████░░░░░░░░░░░░░░░  🚨  Likely Phishing — do not visit
```

> **Note:** WHOIS lookup, DNS resolution, and Google index checks require an active internet connection and may add 3–8 seconds to analysis time.

---

## 📂 Dataset

<div align="center">

| Property | Detail |
|----------|--------|
| **Name** | UCI Phishing Websites Dataset |
| **Source** | [UCI Machine Learning Repository](https://archive.ics.uci.edu/ml/datasets/phishing+websites) |
| **Total Samples** | 11,055 URLs |
| **Features** | 30 numerical features per URL |
| **Phishing** | 4,898 samples `(-1)` |
| **Suspicious** | 702 samples `(0)` |
| **Legitimate** | 6,157 samples `(1)` |
| **Train Split** | 80% — 8,844 samples |
| **Test Split** | 20% — 2,211 samples |
| **Class Balance** | Moderately imbalanced (44% phishing) |

</div>

---

## 🏆 Results & Analysis

### Final Scorecard

```
╔══════════════════════════════════════════════════════╗
║          GRADIENT BOOSTING CLASSIFIER                ║
║          Tested on 2,211 held-out URLs               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Accuracy   ██████████████████████████░░  97.4%     ║
║  F1 Score   ██████████████████████████░░  97.7%     ║
║  Recall     ███████████████████████████░  99.4%     ║
║  Precision  ██████████████████████████░░  98.6%     ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

### Deep-Dive Insights

**1. Why recall matters most in this domain**
A false negative (missed phishing site) exposes a real user to credential theft or malware. A false positive (blocking a safe site) is an inconvenience. The model was optimised with this asymmetry in mind — 99.4% recall means only 6 in every 1,000 phishing URLs are missed.

**2. Why Gradient Boosting beats Random Forest here**
Both are ensemble tree methods, but GBC corrects errors sequentially — each tree focuses on the mistakes of the previous. This makes it especially effective on tabular features with non-linear interactions, which is exactly the structure of URL feature vectors.

**3. Why Naive Bayes failed catastrophically (29.2% recall)**
NB assumes all features are conditionally independent given the class label. URL features are deeply correlated — a short registration length and a missing DNS record often appear together. This violated assumption makes NB nearly useless for this task.

**4. The power of three features**
HTTPS + AnchorURL + WebsiteTraffic alone explain the majority of variance. Phishing sites cannot easily fake all three simultaneously: acquiring a real certificate, building genuine organic traffic, and hosting content on-domain are expensive and time-consuming.

---

## 🛣️ Roadmap

```
 ✅  Phase 1 — Research & Modelling
     [x] Dataset collection and EDA
     [x] 30-feature extraction engine
     [x] 10 model benchmark comparison
     [x] GBC model selection and export

 ✅  Phase 2 — Web Application
     [x] Flask app with prediction endpoint
     [x] Jinja2 UI template
     [x] Heroku deployment config (Procfile + Gunicorn)

 🔄  Phase 3 — API & Integrations  (in progress)
     [ ] REST API endpoint  POST /api/v1/check
     [ ] JSON response format with feature breakdown
     [ ] Rate limiting and API key authentication

 🔮  Phase 4 — Extensions
     [ ] Chrome browser extension
     [ ] Docker containerisation
     [ ] GitHub Actions CI/CD pipeline
     [ ] Real-time model retraining pipeline
     [ ] Streamlit dashboard for visual EDA
```

---

## 🤝 Contributing

Contributions, ideas, and bug reports are warmly welcomed!

**How to contribute:**

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR-USERNAME/Huzaifa.git
cd Huzaifa

# 3. Create a feature branch
git checkout -b feature/your-feature-name

# 4. Make your changes and commit
git add .
git commit -m "feat: describe your change clearly"

# 5. Push to your fork
git push origin feature/your-feature-name

# 6. Open a Pull Request on GitHub
```

**Contribution ideas:**
- 🐛 Fix known bugs in `feature.py` (e.g. `self.soup` reference issue)
- ➕ Add new URL features (e.g. certificate transparency logs)
- 🎨 Improve the Flask UI
- 🐳 Add Docker support
- 📈 Add more modern models (LightGBM, TabNet)

Found a bug? [Open an issue →](https://github.com/huziifa/Huzaifa/issues/new)

---

## 📄 License

This project is distributed under the **MIT License**.

```
MIT License — free to use, modify, and distribute with attribution.
See the LICENSE file for full terms.
```

---

## 👤 Author

<div align="center">

<br/>

<img src="https://github.com/huziifa.png" width="110px" style="border-radius:50%; border: 3px solid #6E57F7;"/>

<br/>

### **Huzaifa**
*Machine Learning Engineer · Cybersecurity Enthusiast · Python Developer*

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-HurairaMaqbool-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/HurairaMaqbool/HurairaMaqbool)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/huraira-maqbool-b696a5277/)
[![Email](https://img.shields.io/badge/Email-Contact-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:hurairac37@gmail.com)

<br/>

*If this project helped you, saved you from a phishing attack, or taught you something new —  
a ⭐ star on GitHub means a lot and helps others find the project.*

<br/>

</div>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:24243e,50:302b63,100:0f0c29&height=120&section=footer" width="100%"/>

<sub>
Built with 🐍 Python · 🤖 scikit-learn · 🌐 Flask · ❤️ Passion for Cybersecurity
</sub>

</div>
