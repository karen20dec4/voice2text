# Raport de audit Voice2Text

Data: 1 noiembrie 2026. Mediu verificat: Windows 10 x64, Python 3.13.3.

## Domeniu și rezultat

Au fost analizate sursele aplicației, interfața, capturarea audio, transcrierea, inserarea textului, configurația și scripturile de lansare/build. Folderul primit nu are metadate Git; autorul și istoricul modificărilor atribuite lui Flash 3.8 nu pot fi confirmați. Constatările de mai jos privesc codul existent la începutul auditului.

Problemele confirmate au fost corectate și protejate prin teste de regresie. O revizie independentă a verificat suplimentar concurența, închiderea și protecția clipboardului. Nu au rămas defecte materiale identificate în acele corecții; aceasta nu reprezintă o garanție că aplicația nu mai conține alte defecte.

## Probleme găsite și corectate

| Prioritate | Problemă și impact | Corecție |
| --- | --- | --- |
| Ridicată | Încărcarea Whisper, shortcuturile și meniul tray apelau Tkinter din fire secundare; trackerul cerea și identificatorul ferestrei prin Tk. Inițializarea și închiderea puteau produce erori de event loop. | Coada `_post_ui` este procesată de firul principal; trackerul exclude ferestrele aplicației după PID, fără apeluri Tk. |
| Ridicată | Trackerul putea schimba destinația în timpul transcrierii; lipirea continua chiar când activarea ferestrei eșua sau ținta dispărea. | Ținta este capturată la începutul dictării. Se verifică existența și focusul înaintea trimiterii tastelor; eșecul păstrează transcrierea într-o fereastră de recuperare. |
| Ridicată | Restaurarea textului simplu distrugea formatele bogate din clipboard și putea suprascrie o copiere nouă a utilizatorului. | `clipboard_guard.py` salvează formatele suportate, folosind blocarea clipboardului Windows. Secvența și proprietarul sunt verificate înaintea restaurării. Formatele nesuportate anulează lipirea înainte de modificarea conținutului. |
| Ridicată | Ieșirea putea termina firul daemon înainte de restaurarea clipboardului sau eliberarea tastelor sintetice. | Oprirea semnalizează anularea și așteaptă finalizarea secțiunii de inserare înainte de distrugerea interfeței. |
| Medie | Shift/Alt/Ctrl/Windows încă apăsate puteau transforma Ctrl+V în alt shortcut. | Așteptare limitată pentru eliberarea modificatoarelor; anulare explicită dacă rămân apăsate. Eliberarea tastelor sintetice este protejată prin `finally`. |
| Ridicată | Reîncărcarea eșuată a unui model păstra modelul vechi sub numele celui nou. Cererile concurente puteau instala un model depășit; starea ocupată era setată prea târziu. | Numele reflectă modelul încărcat efectiv. Cererile au identificatori, ultima cerere prevalează, iar starea ocupată se setează înaintea pornirii firului. Eșecul păstrează modelul anterior și este raportat. |
| Medie | Erorile de inferență erau transformate în text gol, afișat ca „Nimic detectat”. | Erorile ajung la interfață și la jurnal; lipsa vorbirii este tratată separat. |
| Medie | Pornirea microfonului eșuată și erorile la oprire puteau lăsa fluxul audio deschis. | Fluxul se închide și la eșec; bufferul și starea sunt curățate, iar verificarea callbackului se face sub lock. Ieșirea normală oprește microfonul și trackerul. |
| Medie | Un shortcut invalid elimina mai întâi shortcutul funcțional. Fereastra de setări modifica configurația înainte de a afla dacă salvarea reușește. | Shortcutul nou este validat și înregistrat înaintea eliminării celui vechi. Setările se construiesc într-o copie; erorile păstrează dialogul și configurația existentă. |
| Medie | Schimbarea modelului în timpul dictării putea invalida înregistrarea curentă. | Aplicarea setărilor este amânată printr-un mesaj explicit până la terminarea dictării. Parametrii unei sesiuni sunt capturați separat. |
| Medie | Salvarea directă putea trunchia `config.json`; valorile cu tip greșit ajungeau în UI. În pachetul PyInstaller, configurația era calculată relativ la `_internal`. | Salvare atomică prin fișier temporar și `os.replace`, validare la citire, raportarea erorilor și configurație lângă executabil. |
| Medie | Mai multe instanțe puteau înregistra același shortcut și insera text în paralel. | Mutex Windows per sesiune: o a doua instanță se închide fără a inițializa serviciile. |
| Medie | Timerele de resetare puteau ascunde starea unei dictări noi; mutarea butonului putea declanșa dictarea. Controalele din setări puteau depăși înălțimea fixă. | Resetare condiționată de starea curentă, diferențiere între click și drag, conținut de setări derulabil. |
| Medie | Filtrul scriptului de oprire includea chiar procesul PowerShell care conținea numele scriptului și putea potrivi fișiere cu nume doar asemănătoare. | Filtrare după tipul procesului și calea completă, cu delimitarea numelui; suport pentru executabilul din `dist/Voice2Text`. Verificare cu procese simulate, fără oprirea proceselor utilizatorului. |
| Medie | Buildul nu declara explicit toate datele/nativele necesare și anunța succes chiar după eșec. Lipseau manifestele de dependențe. | Manifestele `requirements*.txt`, date CustomTkinter și VAD, biblioteci CTranslate2, verificarea codului de ieșire și preferarea `.venv`. Bibliotecile de conversie a modelelor sunt excluse. |

Au mai fost adăugate jurnalizarea rotativă în `logs/voice2text.log`, `.gitignore` și ghidul [AGENTS.md](AGENTS.md). README explică instalarea, cacheul modelelor, timpii variabili și limitele portabilității. `AGENTS.md` nu exista și a fost creat prin deschidere exclusivă, fără posibilitatea suprascrierii unui fișier existent.

Regulile pentru interacțiunea dintre Tk și fire sunt descrise de [documentația Python](https://docs.python.org/3/library/tkinter.html#threading-model). Verificarea activării ferestrei ține cont de [restricțiile SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow). Protecția datelor respectă modelul de acces explicat în [operațiile Windows Clipboard](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-operations).

## Verificări efectuate

- `python -m unittest discover -s tests -v`: **36 de teste**, inclusiv pornirea și închiderea interfeței reale cu serviciile externe izolate.
- `python tests/native_clipboard_check.py`: test Win32 real pentru text Unicode și formate suplimentare, pe o stație Windows privată. Clipboardul desktopului utilizatorului nu este accesat. Testul a identificat și particularitatea incrementării secvenței la `CloseClipboard`, inclusă în corecție.
- `python -m compileall -q ...`: verificarea compilării surselor și testelor.
- `python -m pip check`: fără dependențe incompatibile raportate în mediul existent.
- Filtrul PowerShell de oprire: executat cu funcții simulate pentru enumerare și oprire; sunt selectate numai procesele aplicației vizate.
- VAD real, cu un vector de tăcere generat: rezultat gol, fără descărcări și fără înregistrare.
- Build PyInstaller final: finalizat cu succes; include `silero_vad_v6.onnx`.
- Executabil final: pornire cu fereastra ascunsă și cache gol, internet dezactivat pentru modelele Hugging Face; eroarea de model absent este gestionată, aplicația rămâne pornită, apoi se închide normal prin `WM_CLOSE`.

Pachetul generat este în `dist/Voice2Text/`, cu executabilul `Voice2Text.exe`. Trebuie păstrat întregul folder, inclusiv `_internal`. Nu conține modelele Whisper și nici configurația folosită la verificarea izolată.

## Limite și comportamente de cunoscut

- Nu a fost efectuată o dictare reală cu microfonul și nici inserare în aplicațiile utilizatorului. Acuratețea românei/englezei, dispozitivele audio și compatibilitatea efectivă cu fiecare terminal necesită o verificare manuală.
- Buildul a fost verificat pe acest Windows 10; Windows 11 și alte calculatoare nu au fost disponibile pentru testare.
- Clipboardul restaurează formatele care pot fi salvate ca șiruri sau octeți. Pentru imagini cu handle GDI, liste de fișiere și alte formate care nu pot fi clonate sigur, aplicația folosește acum introducerea Unicode directă și lasă clipboardul intact. Acest comportament înlocuiește refuzul conservator din prima etapă a auditului.
- Aplicațiile care blochează `Ctrl+V`, ferestrele cu privilegii superioare și schimbările de focus survenite exact în timpul trimiterii tastelor nu permit garantarea universală a inserării. Nu este verificată automat acceptarea textului de către aplicația țintă.
- Prima descărcare a fiecărui model necesită internet. Pentru lucru offline pe alt calculator trebuie pregătit și cacheul modelelor.
- Oprirea forțată din BAT nu poate garanta curățarea clipboardului; ieșirea normală din tray este metoda recomandată. Filtrarea conservatoare poate omite lansările manuale cu o cale relativă.
- Parametrii setărilor sunt salvați lângă surse/executabil; acel folder trebuie să permită scrierea.

Auditul inițial a fost efectuat înainte de conectarea proiectului la Git. Repository-ul actual păstrează licența Apache 2.0 și istoricul importului.

## Completare după verificarea practică: F8 și semnalul audio

Utilizatorul a raportat că F8 nu pornea și nu oprea dictarea din chat. Testul inițial verifica apelarea cozii UI, dar nu mecanismul real de distribuire a evenimentelor din biblioteca `keyboard`.

Problema a fost reprodusă fără taste reale: în `keyboard 0.13.5`, combinația dintre `trigger_on_release=True` și modul implicit nesuprimat caută tasta în tabela tastelor apăsate după eliminarea evenimentului KEY_UP. Callbackul nu este declanșat. Înregistrarea shortcutului folosește acum `suppress=True`; evenimentul este procesat în handlerul sincron, care face doar o adăugare rapidă în coada UI. Testul de regresie execută dispecerul bibliotecii și verifică pornirea și oprirea la două apăsări/eliberări consecutive. Testul eșuează cu implementarea anterioară și trece după corecție.

A fost adăugată o undă verde deschis, bazată pe RMS-ul real al eșantioanelor audio, cu numele microfonului, durata și avertizări pentru lipsa mostrelor, semnal slab sau callback blocat. Nu există animație aleatorie care să simuleze capturarea. Interfața afișează separat timpul scurs la transcriere și etapa de inserare. Jurnalul include evenimentele shortcutului, durata, nivelul maxim și numărul de caractere rezultate, fără salvarea înregistrării sau a transcrierii. Fundalul exterior al ferestrei folosește transparența Windows pentru a elimina dreptunghiul din jurul colțurilor rotunjite.

Microfonul implicit identificat pe sistem este Realtek, confirmat și de utilizator; selecția nu a fost schimbată. Jurnalul anterior conținea atât înregistrări eliminate integral de VAD, cât și una de 41,1 secunde cu aproximativ 6,2 secunde păstrate. Aceste date nu permit atribuirea tuturor încercărilor eșuate lipsei semnalului audio.

Suita actualizată conține **43 de teste**. Au trecut și verificarea clipboardului nativ izolat și compilarea surselor. Comportamentul complet cu vorbire și aplicația chat rămâne de confirmat prin testul interactiv al utilizatorului după repornirea versiunii actualizate.

## Interfață compactă și shortcut F9

Utilizatorul a confirmat funcționarea dictării în chat, apoi a cerut reducerea interfeței, butoane cu aspect Apple și umbră, detalii într-un dropdown, maximum trei rânduri și schimbarea shortcutului în F9.

- Panoul principal are două rânduri; pe ecranul verificat măsoară **266 × 66 px**, față de 394 × 181 px pentru varianta extinsă. Dimensiunea fizică depinde de scalarea Windows.
- Butoanele au colțuri rotunjite, gri neutru, contur fin și umbră discretă în interiorul panoului.
- Indicatorul verde are **96 px** lățime. Mesajele scurte rămân pe un singur rând; erorile lungi nu mai măresc fereastra.
- Meniul „⌄” afișează trei rânduri cu microfonul, modelul/limba/shortcutul și diagnosticul complet. Deschiderea meniului nu redimensionează panoul.
- Colțurile sunt decupate fizic prin [regiunea rotunjită a ferestrei Windows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn), pe lângă transparența culorii de fundal. Verificarea nativă confirmă că pixelul din colț este în afara regiunii vizibile.
- F9 este implicit în surse și setări. Instanța veche a fost închisă normal, configurația utilizatorului a fost actualizată la F9, apoi aplicația a fost repornită.

**45 de teste trecute**, inclusiv dimensiunile panoului, limita indicatorului, păstrarea diagnosticului complet, dropdownul și conturul nativ. Verificarea clipboardului izolat și compilarea surselor trec. Executabilul din `dist/Voice2Text` a fost regenerat; interfața instanței pornite a fost verificată vizual, fără înregistrare sau inserare automată în timpul verificării.

## Referință vizuală, mutarea întregului panou și Print Screen

Interfața este adaptată după `record-voice-upgrade.png`, indicată de utilizator: buton principal albastru cu contur cyan, comenzi grafit și indicator verde segmentat. Fundalurile și pictogramele sunt PNG-uri RGBA cu canal alfa real, generate din sursa editabilă `icon_generator.py` și păstrate în `assets/`. `ui_controls.py` compune aceste imagini cu text lizibil; nu mai sunt folosite simboluri emoji pentru butoane. Panoul păstrează două rânduri, indicatorul de 96 px, dropdownul și F9.

Mutarea folosește un tag Tk plasat înaintea handlerelor interne pe toate suprafețele reale: cadre, canvasuri, etichete, pictograme și butoane. `CTkFrame.winfo_children()` ascunde canvasul propriu; implementarea folosește metoda de bază Tk pentru a-l include. O tragere consumă eliberarea mouse-ului înaintea acțiunii butonului, iar un click simplu continuă să funcționeze. Testul GUI produce evenimente Tk pe o fereastră invizibilă și verifică mutarea efectivă fără dictare sau deschiderea setărilor.

Eroarea raportată după Print Screen provenea din refuzul clonării unui handle de imagine. Pentru asemenea formate, aplicația folosește [SendInput](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput) cu [KEYEVENTF_UNICODE](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput), fără golirea sau înlocuirea clipboardului. Verifică focusul și modificatoarele, păstrează perechile UTF-16 în același lot și eliberează ultima tastă dacă Windows acceptă doar o parte din evenimente. Erorile păstrează transcrierea pentru recuperare. Introducerea efectivă depinde în continuare de aplicația țintă și de nivelul de privilegii.

**49 de teste trecute** și verificare nativă pe o stație privată, cu HBITMAP și DIB reale. Conținutul imaginii rămâne identic după operație. Doar trimiterea tastelor este simulată; testele nu accesează clipboardul interactiv și nu introduc text în aplicațiile utilizatorului. Buildul include acum și folderul `assets/`.

## Încărcarea modelului medium fără consolă

La schimbarea spre `medium`, interfața răspundea la mesaje Windows, dar patru fișiere temporare rămâneau la zero bytes. Serverul răspundea normal la verificările HTTP. Un proces `pythonw` separat a reprodus eroarea `AttributeError: 'NoneType' object has no attribute 'write'`: bara de progres per fișier din Hugging Face/tqdm încerca să scrie în `sys.stderr`, inexistent fără consolă. În descărcarea paralelă, aceasta poate lăsa alți workeri în așteptarea lockului de progres.

`WhisperTranscriber` dezactivează acum barele de progres Hugging Face înaintea pornirii workerilor atunci când `sys.stderr is None`. Testul nou execută `pythonw` și tqdm real, fără rețea sau descărcare de model. **50 de teste trec.** Variabila `HF_HUB_DISABLE_PROGRESS_BARS=0` ar împiedica dezactivarea explicită; ea nu este prezentă în mediul verificat.

Instanța afectată a fost închisă; workerii blocați împiedicau terminarea procesului, deci procesul respectiv a fost terminat după închiderea interfeței. Aplicația corectată a repornit cu selecția `medium` păstrată. Descărcarea reală a fișierului de aproximativ 1,53 GB a trecut imediat de zero bytes și a fost observată crescând. Nu a fost necesară instalarea `hf_xet`.

Descărcarea s-a încheiat, fără fișiere incomplete rămase. La 20:53:03 jurnalul a confirmat `Model Whisper pregătit: medium`. Executabilul a fost regenerat cu aceeași corecție.

## Migrare, denumire Voice2Text și repository

Proiectul a fost mutat în `H:/_Proiecte/Voice2Text` și redenumit integral în surse, interfață, tray, mutex și lansatoare. Repository-ul este [karen20dec4/voice2text](https://github.com/karen20dec4/voice2text), cu istoricul inițial și licența Apache 2.0 păstrate.

Executabilul se află direct în rădăcină, ca `Voice2Text.exe`, împreună cu `_internal/`. Sursele și binarul rezolvă cacheul la `models/`, iar jurnalele la `logs/`. Modelele `base`, `small` și `medium` au fost verificate prin SHA-256; cele 12 symlinkuri relative ale snapshoturilor sunt valide. `medium` s-a încărcat offline din noua locație, iar executabilul pornit prin shortcut a confirmat ulterior starea pregătită.

Shortcutul Desktop `Voice2Text.lnk` indică executabilul și folderul de lucru din H:. Pictograma are sursă vectorială `icon.svg` și format Windows `icon.ico` cu șapte rezoluții, de la 16 la 256 px; este inclusă și în executabil. `Create-Desktop-Shortcut.ps1` poate reface legătura după o mutare ulterioară.

Buildul verifică și rezervă mutexul aplicației pe durata instalării, evitând suprascrierea unui bundle pornit în timpul compilării. **55 de teste trecute**, verificare nativă izolată a clipboardului, build final și pornire reală din H: cu `medium` pregătit. Modelele, binarele, configurația personală, jurnalele și `.migration-backup/` sunt excluse din Git. Copiile originale ale cacheului, vechiul build și shortcutul anterior sunt păstrate în backupul local de migrare.
