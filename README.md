# Voice2Text

<img src="icon.png" width="88" alt="Voice2Text">

Utilitar Windows de dictare vocală în română și engleză, cu transcriere locală Whisper pe placa video sau pe procesor. Panoul compact are două rânduri, butoane cu imagini transparente, indicator audio de 96 px și un meniu cu informații suplimentare.

## Utilizare

1. Pornește `Voice2Text.exe` sau `Start-Voice2Text.bat`. Se deschide doar panoul; înregistrarea nu pornește singură. O a doua lansare afișează panoul existent.
2. Așteaptă încărcarea modelului și selectează câmpul în care vrei textul.
3. Apasă **F9** sau **Dictează**, vorbește, apoi oprește la fel. Butonul este roșu deschis cât timp înregistrează.
4. Așteaptă transcrierea și verifică textul inserat. Enter automat este dezactivat implicit.

Panoul poate fi mutat prin tragere din orice zonă, inclusiv de pe butoane și pictograme. Un click simplu păstrează acțiunea butonului. Meniul **⌄** afișează microfonul, modelul, limba și diagnosticul complet; rotița deschide setările. Click pe pictograma din tray arată sau ascunde panoul; dictarea din tray se pornește explicit din meniu.

În terminale (consola Windows, Windows Terminal, ConEmu, mintty), inclusiv în sesiunile Claude Code CLI, textul este tastat direct prin Unicode: `Ctrl+V` nu lipește într-o aplicație CLI în mod raw din consola clasică. Fiecare dictare merge în fereastra activă la pornirea ei, deci poți folosi oricâte sesiuni. Rămâi în acea fereastră până apare textul; dacă focusul nu poate fi readus, transcrierea este oferită pentru recuperare.

În celelalte aplicații, textul folosește o lipire protejată când clipboardul poate fi restaurat. Dacă ai copiat o captură de ecran sau fișiere, introducerea Unicode păstrează clipboardul intact. Suportul depinde de aplicația țintă; ferestrele cu privilegii mai mari pot bloca introducerea. Erorile oferă transcrierea pentru recuperare manuală.

Panoul devine violet deschis când dictarea nu merge într-o fereastră Claude (Claude Code în terminal sau aplicația Claude). Textul este trimis și acolo, dar o lipire într-o fereastră fără câmp de text se pierde fără nicio eroare, așa că verifică destinația în meniul **⌄**, pe rândul **Trimit în**. Ultimele 10 transcrieri rămân în același meniu până închizi aplicația; un click deschide textul, cu buton de copiere. Ele stau doar în memorie, nu pe disc.

Ieși normal din meniul tray pentru eliberarea resurselor. `Stop-Voice2Text.bat` este o oprire forțată pentru instanțele din acest folder.

## Totul în folderul proiectului

| Cale | Rol |
| --- | --- |
| `Voice2Text.exe` | Aplicația compilată, în rădăcina proiectului |
| `_internal/` | Bibliotecile și resursele necesare executabilului |
| `models/` | Cacheul local pentru modelele Whisper |
| `gpu/` | Motorul Vulkan, din `Build-GPU-Engine.bat` |
| `cuda/` | Bibliotecile NVIDIA opționale, din `Install-CUDA-Libs.ps1` |
| `config.json` | Setările personale, lângă executabil/surse |
| `logs/voice2text.log` | Jurnal rotativ cu metadate și erori |

Setările listează doar microfoanele care acceptă captura la 16 kHz. Panoul se deschide la fiecare lansare, chiar dacă a fost ascuns anterior; o poziție salvată pe un monitor deconectat revine într-o zonă vizibilă.

Sursele și executabilul folosesc același `models/`, calculat relativ la locația aplicației, fără o cale fixă spre un anumit disc. Prima utilizare a unui model necesită internet. Modelele deja descărcate pot fi folosite offline. Înregistrările și transcrierile nu sunt salvate intenționat în jurnal.

Pentru portabilitate, păstrează executabilul împreună cu `_internal/`, `models/` și `gpu/`. Folderul trebuie să permită scrierea. Modelele, configurația, jurnalele și binarele generate sunt excluse din Git.

## Placă video

Setarea **Procesare** alege între **GPU** și **CPU**, iar **Model Whisper** rămâne separat. Pe GPU, ordinea este: CUDA pe plăci NVIDIA cu biblioteci instalate, apoi Vulkan pe orice placă modernă (AMD, NVIDIA, Intel), apoi CPU. Dacă GPU-ul eșuează la încărcare, aplicația continuă pe CPU și notează motivul în jurnal. Meniul **⌄** arată unde rulează modelul.

Vulkan folosește `gpu/voice2text_whisper.dll` și modele comprimate în `models/ggml/`, descărcate la prima utilizare: `medium-q5_0` are 514 MB. `Build-GPU-Engine.bat` compilează DLL-ul (necesită Visual Studio Build Tools); păstrează `gpu/` lângă executabil.

Pentru CUDA, rulează o dată `.\Install-CUDA-Libs.ps1` (circa 1,3 GB), apoi repornește aplicația. Această cale nu a fost rulată încă pe o placă NVIDIA reală.

Timpi măsurați pe RX 6800 XT și Ryzen 9 5950X, cu modelul `medium`, pentru o frază de 4 s:

| Procesare | Timp |
| --- | --- |
| CPU, 4 fire | 7,6 s |
| CPU, 8 fire (setarea actuală) | 6,1 s |
| GPU Vulkan, `medium-q5_0` | 1,4 s |

Modelul ocupă circa 870 MB de memorie video cât timp aplicația este deschisă. Pornește aplicația înainte de a încărca modele mari în LM Studio: comportamentul cu memoria video plină nu a fost testat.

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

Testele izolează microfonul, descărcările și trimiterea tastelor. Verificarea nativă folosește un clipboard privat, separat de desktopul utilizatorului. Testele includ pornirea fără consolă și fără înregistrare, schimbarea modelelor, protecția clipboardului, rutarea inserării în terminale și interacțiunile panoului.

Detalii istorice despre corecții: [AUDIT_REPORT.md](AUDIT_REPORT.md). Ghid pentru contribuții: [AGENTS.md](AGENTS.md).

## Licență

Codul este distribuit sub [Apache License 2.0](LICENSE). Modelele și dependențele își păstrează propriile licențe.
