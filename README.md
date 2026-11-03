# Voice2Text

<img src="icon.png" width="88" alt="Voice2Text">

Utilitar Windows de dictare vocală în română și engleză, cu transcriere locală Whisper pe placa video sau pe procesor. Panoul compact are două rânduri, butoane cu imagini transparente, indicator audio de 86 px și un meniu cu informații suplimentare.

## Utilizare

1. Pornește `Voice2Text.exe` sau `Start-Voice2Text.bat`. Se deschide doar panoul; înregistrarea nu pornește singură. O a doua lansare afișează panoul existent.
2. Așteaptă încărcarea modelului și selectează câmpul în care vrei textul.
3. Apasă **F9** sau **Dictează**, vorbește, apoi oprește la fel. Butonul este roșu deschis cât timp înregistrează.
4. Textul apare în timp ce vorbești: la fiecare pauză de circa 0,6 s, fraza spusă este transcrisă și inserată. Dacă vorbești continuu, segmentul se încheie la prima respirație după 12 s. La oprire se transcrie restul, iar Enter automat (dezactivat implicit) se apasă o singură dată, la final.

Primul rând al panoului arată versiunea aplicației (de exemplu `v1.6.0`), lângă **Dictează**. Panoul poate fi mutat prin tragere din orice zonă, inclusiv de pe butoane și pictograme. Un click simplu păstrează acțiunea butonului. Meniul **⌄** afișează microfonul, modelul, limba și diagnosticul complet; rotița deschide setările, iar **×** închide aplicația (cere confirmare doar în timpul unei dictări). Click pe pictograma din tray arată sau ascunde panoul; dictarea din tray se pornește explicit din meniu.

Shortcutul este înregistrat la Windows prin `RegisterHotKey`, deci funcționează în orice fereastră neelevată și nu se dezactivează singur cât timp aplicația rulează. Dacă altă aplicație folosește deja combinația, setările refuză salvarea cu un mesaj. La pornire, un shortcut ocupat revine la F9; dacă și F9 este ocupat, dictarea pornește doar din panou, iar motivul apare în jurnal.

În terminale (consola Windows, Windows Terminal, ConEmu, mintty, PuTTY, KiTTY), inclusiv în sesiunile Claude Code CLI locale sau pe un server prin SSH și tmux, textul este tastat direct prin Unicode: `Ctrl+V` nu lipește într-o aplicație CLI în mod raw din consola clasică, iar PuTTY îl trimite serverului ca `^V`. Fiecare dictare merge în fereastra activă la pornirea ei, deci poți folosi oricâte sesiuni. Dacă treci în altă fereastră în timpul dictării, frazele așteaptă și nu îți fură focusul; ele ajung în fereastra inițială când revii sau când oprești dictarea. Dacă focusul nu poate fi readus, textul încă neinserat este oferit pentru recuperare.

În celelalte aplicații, textul folosește o lipire protejată când clipboardul poate fi restaurat. Dacă ai copiat o captură de ecran sau fișiere, introducerea Unicode păstrează clipboardul intact. Suportul depinde de aplicația țintă; ferestrele cu privilegii mai mari pot bloca introducerea. Erorile oferă transcrierea pentru recuperare manuală.

Panoul devine violet deschis când dictarea nu merge într-o fereastră Claude (Claude Code în terminal sau aplicația Claude). Textul este trimis și acolo, dar o lipire într-o fereastră fără câmp de text se pierde fără nicio eroare, așa că verifică destinația în meniul **⌄**, pe rândul **Trimit în**. Ultimele 10 transcrieri rămân în același meniu până închizi aplicația; un click deschide textul, cu buton de copiere. Ele stau doar în memorie, nu pe disc. Claude pornit pe un server prin PuTTY nu poate fi recunoscut din Windows, deci acolo panoul rămâne violet deși textul ajunge corect.

Pentru diacritice într-o sesiune PuTTY, setează **Window → Translation → Remote character set: UTF-8**, iar pe server un `locale` UTF-8. Pe un server fără UTF-8, bifează în setări **Scrie fără diacritice**: textul tastat devine ASCII (`ă`→`a`, `ș`→`s`, ghilimelele „” devin `"`, `…` devine `...`). Istoricul și recuperarea păstrează transcrierea originală. Opțiunea se aplică în toate ferestrele, așa că dezactiveaz-o când revii la aplicații cu diacritice.

Ieși normal cu **×** sau din meniul tray pentru eliberarea resurselor. `Stop-Voice2Text.bat` este o oprire forțată pentru instanțele din acest folder.

## Segmentare în timp real

În timpul înregistrării, `live_transcription.py` verifică la fiecare 0,2 s audio-ul netranscris, cu detectorul de voce Silero din `faster-whisper`. Un segment se încheie astfel:

| Situație | Unde se taie |
| --- | --- |
| Pauză de cel puțin 0,6 s după vorbire | La 0,2 s după ultimul sunet, ca finalul frazei să nu fie tăiat |
| Segment de peste 12 s fără pauză lungă | La mijlocul ultimei pauze de cel puțin 0,15 s (o respirație) |
| Segment de 28 s fără nicio pauză | Exact la 28 s |
| Oprirea dictării | Tot ce a rămas |

Sunetele sub 0,25 s (click, tuse) nu contează ca vorbire, pentru că Whisper tinde să le transforme în text inventat. Segmentele se procesează pe rând, pe un singur fir: audio-ul captat între timp așteaptă, deci un model mai lent produce segmente mai mari, nu pierde text. Dacă o transcriere eșuează în timpul dictării, restul audio-ului se reia întreg la oprire.

Pe RX 6800 XT cu `medium`, textul apare la circa 1,1–1,5 s după pauză. Fiecare segment se transcrie fără contextul celor anterioare, așa că o pauză în mijlocul frazei poate produce punct sau literă mare.

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

Pe un Mac cu Boot Camp, driverul AMD instalat de Apple poate oferi doar Vulkan 1.1, iar whisper.cpp cere Vulkan 1.2 (`ggml_vulkan: Error: Vulkan 1.2 required.` în jurnal, apoi rulare pe CPU). Driverul AMD Boot Camp oficial (Unified Driver R6.4, 21.30.45.22, de pe pagina AMD „Apple Boot Camp”) aduce Vulkan 1.2 pe Radeon Pro 575.

Pentru CUDA, rulează o dată `.\Install-CUDA-Libs.ps1` (circa 1,3 GB), apoi repornește aplicația. Această cale nu a fost rulată încă pe o placă NVIDIA reală.

Timpi măsurați pe RX 6800 XT și Ryzen 9 5950X, cu modelul `medium`, pentru o frază de 4 s:

| Procesare | Timp |
| --- | --- |
| CPU, 4 fire | 7,6 s |
| CPU, 8 fire (setarea actuală) | 6,1 s |
| GPU Vulkan, `medium-q5_0` | 1,4 s |

Pe un iMac 2017 (i7-7700, Radeon Pro 575), pentru o frază de 5,3 s:

| Model | CPU, 4 fire | GPU Vulkan |
| --- | --- | --- |
| `small` | 2,4 s | 1,5 s |
| `medium` | 6,9 s | 3,0 s |

Pe GPU și pe CPU, `medium` greșește la fel de des: diferențele pe 120 de fraze din Common Voice și pe înregistrări proprii au fost de 1–3 cuvinte la sută, în ambele sensuri. Comprimarea `q5_0` nu contează: `q8_0` și modelul complet au dat aceleași rezultate. Pentru română, ambele motoare primesc un text inițial cu diacritice. Fără el, Whisper omitea diacriticele la circa o treime din fraze, la întâmplare; pe două înregistrări de 60 s, rata de cuvinte greșite a scăzut pe GPU de la 29% la 7% și de la 16% la 5%. Rar, pe audio neclar, Whisper repetă acest text; o asemenea frază nu se inserează.

Modelul ocupă circa 870 MB de memorie video cât timp aplicația este deschisă. Pornește aplicația înainte de a încărca modele mari în LM Studio: comportamentul cu memoria video plină nu a fost testat.

## Dezvoltare și build

Mediu verificat: Windows 10 x64 cu Python 3.13 și Python 3.14. Windows 11 trebuie verificat pe sistemul țintă.

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

Testele izolează microfonul, descărcările și trimiterea tastelor. Verificarea nativă folosește un clipboard privat, separat de desktopul utilizatorului. Testele includ pornirea fără consolă și fără înregistrare, schimbarea modelelor, segmentarea la pauze, protecția clipboardului, rutarea inserării în terminale și interacțiunile panoului.

Detalii istorice despre corecții: [AUDIT_REPORT.md](AUDIT_REPORT.md). Ghid pentru contribuții: [AGENTS.md](AGENTS.md).

## Licență

Codul este distribuit sub [Apache License 2.0](LICENSE). Modelele și dependențele își păstrează propriile licențe.
