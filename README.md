# 🎮 Project Epoch Multi-Server Monitor

![Server Monitor UI](resources/sampleUI.png)

**Real-time monitoring for Project Epoch WoW servers with smart notifications, auto-launch, and enhanced stability!**

Monitor Auth, Kezan (PvE), and Gurubashi (PvP) servers simultaneously with sound alerts when realms come online.

## 🚀 Download & Install

### ⚡ Easy Way (Recommended)
1. **[📥 Download Latest Release](https://github.com/desuqcafe/Lazy-Project-Epoc-Monitor/releases/latest)**
2. **📂 Extract the zip file anywhere**
3. **🖱️ Double-click `ProjectEpochMonitor.exe`**
4. **🎉 That's it! No Python needed!**

### 👩‍💻 Developer Way
```bash
git clone https://github.com/desuqcafe/Lazy-Project-Epoc-Monitor.git
cd Lazy-Project-Epoc-Monitor
pip install -r requirements.txt
python monitor.py
```

## ✨ Key Features

### 🌐 **Multi-Server Monitoring**
- **Auth Server** (Login): `game.project-epoch.net:3724`
- **Kezan** (PvE Realm): `game.project-epoch.net:8085` 
- **Gurubashi** (PvP Realm): `game.project-epoch.net:8086`
- Individual enable/disable controls per server
- Real-time connection quality detection
- Enhanced connection rejection detection

### 🔔 **Smart Notifications**
- 🔊 **Sound alerts** when Kezan/Gurubashi come online
- 🎵 **Custom notification sounds** (place MP3/WAV files in `resources/audio/`)
- 🎚️ **Volume control** with test button
- 🧠 **Smart logic**: Only alerts when Auth server is also online

### 🎮 **Auto Client Management**
- **Auto-launch** your WoW client when realms come UP
- **Smart window detection** and focusing
- **Test buttons** to verify everything works
- Support for any Project Epoch launcher/client

### 📊 **Enhanced Monitoring**
- **Connection quality indicators**: 🟢🟡🟠🔴🚫
- **Uptime statistics** for each server
- **Active IP detection** for better reliability
- **Timeout vs offline** distinction
- **Activity logging** with timestamps

### ⚙️ **Quality of Life**
- **No more UI freezing** when toggling servers! ✅
- **Persistent settings** - remembers your preferences
- **Dark theme** UI that's easy on the eyes
- **Configurable check intervals** (2-300 seconds)
- **Window position memory** across restarts

## 🏃‍♀️ Quick Start

1. **🚀 Launch** `ProjectEpochMonitor.exe`
2. **🎯 Configure** (optional):
   - Browse to your Project Epoch launcher
   - Choose auto-action when realms come UP
   - Test your notification sound
3. **▶️ Click "Start All"** to begin monitoring
4. **🎉 Get notified** the moment realms are online!

### 🔧 Test Everything Works
- **🔊 Test Sound** - Make sure audio notifications work
- **🖼️ Test Focus** - Verify window detection works  
- **🌐 Detect Active IPs** - Check connection detection

## 🎵 Custom Notification Sounds

Want your own notification sound? Easy! 

1. **📁 Navigate to** `resources/audio/` folder
2. **📥 Drop in** your MP3/WAV/OGG files  
3. **🔄 Restart** the monitor
4. **🎚️ Select** your sound from the dropdown!

*Comes with `gotime.mp3` by default* 🎶

## 🚨 Why This Monitor?

**Perfect for Project Epoch's launch period!** Get notified the **instant** servers come online:

- ✅ **No more manual refreshing** server lists
- ✅ **No more missing** the launch window  
- ✅ **Auto-launch** your client immediately
- ✅ **Multi-server awareness** - know which realm to pick
- ✅ **Connection quality** - avoid servers having issues

## 🐛 Troubleshooting

### 🔇 No Sound?
- Check volume slider isn't at 0
- Try "Test Sound" button
- Make sure `resources/audio/` folder exists

### 🚫 Connection Issues?
- **Run as Administrator** for better network detection
- Check Windows Firewall isn't blocking
- Try "Detect Active IPs" button

### 🎮 Client Launch Problems?
- Use "Browse" to select your exact launcher
- Try "Test Launch" button first
- Make sure executable path is correct

### ❄️ App Freezing?
- This was fixed in v2.0! Update to latest release ✅

## 📋 System Requirements

- **Windows 10/11** (tested)
- **No Python required** for executable version
- **~50MB** disk space
- **Network access** to `game.project-epoch.net`

## 📜 Version History

**v2.0.0** - Major Stability Update ✨
- Fixed UI freezing when toggling servers
- Added volume control and test sound button  
- Enhanced connection quality detection
- Improved thread management and cleanup
- Better error handling throughout

**v1.x** - Initial releases with basic monitoring

---

## 💝 Final Notes

*This monitor will probably only be useful for a week or two during Project Epoch's launch period - but it'll make those crucial first days SO much smoother!* 😄

**Enjoy the launch, and may your realm always be online!** 🎮✨

---

*Found a bug? Have a suggestion? [Open an issue](https://github.com/desuqcafe/Lazy-Project-Epoc-Monitor/issues)!*