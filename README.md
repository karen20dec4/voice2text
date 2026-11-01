# Voice2Text

<img src="icon.png" width="88" alt="Voice2Text">

Utilitar Windows de dictare vocală în română și engleză, cu transcriere locală prin faster-whisper. Panoul compact are două rânduri, butoane cu imagini transparente, indicator audio de 96 px și un meniu cu informații suplimentare.

## Utilizare

1. Pornește `Voice2Text.exe` sau `Start-Voice2Text.bat`.
2. Așteaptă încărcarea modelului și selectează câmpul în care vrei textul.
3. Apasă **F9**, vorbește, apoi apasă din nou **F9**.
4. Așteaptă transcrierea și verifică textul inserat. Enter automat este dezactivat implicit.

Panoul poate fi mutat prin tragere din orice zonă, inclusiv de pe butoane și pictograme. Un click simplu păstrează acțiunea butonului. Meniul **⌄** afișează microfonul, modelul, limba și diagnosticul complet; rotița deschide setările.

Textul folosește o lipire protejată când clipboardul poate fi restaurat. Dacă ai copiat o captură de ecran sau fișiere, introducerea Unicode păstrează clipboardul intact. Suportul depinde de aplicația țintă; ferestrele cu privilegii mai mari pot bloca introducerea. Erorile oferă transcrierea pentru recuperare manuală.

Ieși normal din meniul tray pentru eliberarea resurselor. `Stop-Voice2Text.bat` este o oprire forțată pentru instanțele din acest folder.

## Totul în folderul proiectului

| Cale | Rol |
| --- | --- |
| `Voice2Text.exe` | Aplicația compilată, în rădăcina proiectului |
| `_internal/` | Bibliotecile și resursele necesare executabilului |
| `models/` | Cacheul local pentru modelele Whisper |
| `config.json` | Setările personale, lângă executabil/surse |
| `logs/voice2text.log` | Jurnal rotativ cu metadate și erori |

Sursele și executabilul folosesc același `models/`, calculat relativ la locația aplicației, fără o cale fixă spre un anumit disc. Prima utilizare a unui model necesită internet. Modelele deja descărcate pot fi folosite offline. Înregistrările și transcrierile nu sunt salvate intenționat în jurnal.

Pentru portabilitate, păstrează executabilul împreună cu `_internal/` și `models/`. Folderul trebuie să permită scrierea. Modelele, configurația, jurnalele și binarele generate sunt excluse din Git.

## Dezvoltare și build

Mediu verificat: Windows 10 x64 și Python 3.13. Windows 11 trebuie verificat pe sistemul țintă.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe Voice2Text.pyw
```

Pentru executabil:

```powershell
.\Build-Portable-EXE.bat
```

Închide aplicația înainte de build. Scriptul compilează în `.build/`, apoi instalează `Voice2Text.exe` și `_internal/` în rădăcina proiectului. Cacheul `models/` și configurația sunt păstrate. `Start-Voice2Text.bat` preferă executabilul existent; pentru modificări de cod rulează explicit sursa sau regenerează buildul.

Pictograma editabilă este `icon.svg`; `icon.ico` conține rezoluții de la 16 la 256 px. `python icon_generator.py` regenerează pictogramele și resursele UI.

## Shortcut Desktop

După build:

```powershell
.\Create-Desktop-Shortcut.ps1
```

Scriptul creează `Voice2Text.lnk`, cu executabilul, folderul de lucru și pictograma `icon.ico` din locația curentă a proiectului. Rulează-l din nou după mutarea folderului.

## Verificare

```powershell
python -m unittest discover -s tests -v
python tests/native_clipboard_check.py
```

Testele izolează microfonul, descărcările și trimiterea tastelor. Verificarea nativă folosește un clipboard privat, separat de desktopul utilizatorului. Testele includ pornirea fără consolă, schimbarea modelelor, protecția clipboardului și interacțiunile panoului.

Detalii istorice despre corecții: [AUDIT_REPORT.md](AUDIT_REPORT.md). Ghid pentru contribuții: [AGENTS.md](AGENTS.md).

## Licență

Codul este distribuit sub [Apache License 2.0](LICENSE). Modelele și dependențele își păstrează propriile licențe.
