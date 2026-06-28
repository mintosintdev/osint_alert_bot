use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{
    App, AppHandle, Emitter, Manager, Runtime, State,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

pub struct BackendProcess(pub Arc<Mutex<Option<CommandChild>>>);
pub struct AppState {
    pub backend_ready: Arc<Mutex<bool>>,
    pub backend_port: u16,
}

#[tauri::command]
async fn notify(app: AppHandle, title: String, body: String, urgent: bool) {
    let _ = app.notification().builder().title(&title).body(&body).show();
    if urgent { eprintln!("[NOTIFY] URGENT: {} - {}", title, body); }
}

#[tauri::command]
async fn keychain_set(service: String, key: String, value: String) -> Result<(), String> {
    let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
    entry.set_password(&value).map_err(|e| e.to_string())
}

#[tauri::command]
async fn keychain_get(service: String, key: String) -> Result<String, String> {
    let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
    entry.get_password().map_err(|e| e.to_string())
}

#[tauri::command]
async fn keychain_delete(service: String, key: String) -> Result<(), String> {
    let entry = keyring::Entry::new(&service, &key).map_err(|e| e.to_string())?;
    entry.delete_credential().map_err(|e| e.to_string())
}

#[tauri::command]
async fn backend_health(state: State<'_, AppState>) -> Result<bool, String> {
    let port = state.backend_port;
    match reqwest::get(format!("http://127.0.0.1:{}/api/stats", port)).await {
        Ok(r) => Ok(r.status().is_success()),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
fn get_backend_port(state: State<'_, AppState>) -> u16 { state.backend_port }

#[tauri::command]
fn show_window(app: AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show(); let _ = win.set_focus();
    }
}

#[tauri::command]
fn hide_to_tray(app: AppHandle) {
    if let Some(win) = app.get_webview_window("main") { let _ = win.hide(); }
}

#[tauri::command]
async fn open_url(app: AppHandle, url: String) {
    // використовуємо xdg-open напряму
    let _ = app.shell().command("xdg-open").args([&url]).spawn();
}

#[tauri::command]
async fn read_file(path: String) -> Result<String, String> {
    tokio::fs::read_to_string(&path).await.map_err(|e| e.to_string())
}

fn start_backend(app: &App) -> Result<CommandChild, Box<dyn std::error::Error>> {
    let (_, child) = app.shell().sidecar("backend")?.spawn()?;
    Ok(child)
}

async fn wait_for_backend(port: u16, max_attempts: u32) -> bool {
    let client = reqwest::Client::new();
    for attempt in 0..max_attempts {
        tokio::time::sleep(Duration::from_millis(500)).await;
        if let Ok(r) = client
            .get(format!("http://127.0.0.1:{}/api/stats", port))
            .timeout(Duration::from_secs(2))
            .send().await
        {
            if r.status().is_success() {
                eprintln!("[SIDECAR] Ready after {} attempts", attempt + 1);
                return true;
            }
        }
        eprintln!("[SIDECAR] Waiting... attempt {}", attempt + 1);
    }
    false
}

fn build_tray<R: Runtime>(app: &App<R>) -> tauri::Result<()> {
    let show  = MenuItem::with_id(app, "show",  "Show Border Sentinel", true, None::<&str>)?;
    let search = MenuItem::with_id(app, "search", "Quick Search", true, None::<&str>)?;
    let sep   = tauri::menu::PredefinedMenuItem::separator(app)?;
    let quit  = MenuItem::with_id(app, "quit",  "Quit", true, None::<&str>)?;
    let menu  = Menu::with_items(app, &[&show, &search, &sep, &quit])?;

    TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.show(); let _ = win.set_focus();
                }
            }
            "search" => {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.show(); let _ = win.set_focus();
                    let _ = win.emit("focus-search", ());
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up, ..
            } = event {
                let app = tray.app_handle();
                if let Some(win) = app.get_webview_window("main") {
                    if win.is_visible().unwrap_or(false) { let _ = win.hide(); }
                    else { let _ = win.show(); let _ = win.set_focus(); }
                }
            }
        })
        .build(app)?;
    Ok(())
}

fn register_hotkeys<R: Runtime>(app: &App<R>) -> tauri::Result<()> {
    let show_search = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyS);
    let hide_key    = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyH);
    let panic_key   = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyP);

    app.global_shortcut().on_shortcuts(
        [show_search, hide_key, panic_key],
        move |app, shortcut, _state| {
            let win = app.get_webview_window("main");
            match shortcut.key {
                Code::KeyS => {
                    if let Some(win) = win {
                        let _ = win.show(); let _ = win.set_focus();
                        let _ = win.emit("focus-search", ());
                    }
                }
                Code::KeyH | Code::KeyP => {
                    if let Some(win) = win { let _ = win.hide(); }
                }
                _ => {}
            }
        },
    ).map_err(|e| tauri::Error::Anyhow(anyhow::anyhow!(e.to_string())))?;

    Ok(())
}

pub fn run() {
    let backend_port: u16 = 8000;

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .manage(AppState {
            backend_ready: Arc::new(Mutex::new(false)),
            backend_port,
        })
        .manage(BackendProcess(Arc::new(Mutex::new(None))))
        .setup(move |app| {
            build_tray(app)?;
            register_hotkeys(app)?;

            let backend_process = app.state::<BackendProcess>();
            match start_backend(app) {
                Ok(child) => {
                    *backend_process.0.lock().unwrap() = Some(child);
                    eprintln!("[SIDECAR] Python backend started");
                }
                Err(e) => eprintln!("[SIDECAR] Failed: {}", e),
            }

            let app_handle = app.handle().clone();
            let ready_flag = app.state::<AppState>().backend_ready.clone();

            tauri::async_runtime::spawn(async move {
                let ready = wait_for_backend(backend_port, 30).await;
                *ready_flag.lock().unwrap() = ready;
                if let Some(win) = app_handle.get_webview_window("main") {
                    if ready {
                        let _ = win.emit("backend-ready", ());
                    } else {
                        let _ = win.emit("backend-error", "Backend failed to start");
                    }
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            notify, keychain_set, keychain_get, keychain_delete,
            backend_health, get_backend_port,
            show_window, hide_to_tray, open_url, read_file,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Border Sentinel");
}
