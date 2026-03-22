import lmdb
import json


default_lang_map = {
    "English": {"trans_lang": "en", "tts_lang": ["en-US"]},
    "Chinese (Simplified)": {"trans_lang": "zh-CN", "tts_lang": ["zh-CN", "zh-Hans"]},
    "Chinese (Traditional)": {"trans_lang": "zh-TW", "tts_lang": ["zh-TW", "zh-HK"]},
    "Japanese": {"trans_lang": "ja", "tts_lang": ["ja-JP"]},
    "Korean": {"trans_lang": "ko", "tts_lang": ["ko-KR"]},
}

default_settings = {
    "settings_open": False,
    "is_pinned": False,
    "enable_translation": False,
    "target_lang": "English",
    "hotkey_settings": {
        "background_process_hotkey": {
            "enable": True,
            "hotkey": "ctrl+shift+x",
        },
        "application_invoke_hotkey": {
            "enable": True,
            "hotkey": "ctrl+shift+q",
        },
    },
    "enable_focus_dim": True,
    "idle_opacity": 1,
    "current_img": None,
    "ocr_langs": "chi_sim+chi_sim_vert+chi_tra+chi_tra_vert+eng+kor+jpn+vie",
    # Transfer Hub: listen on LAN (0.0.0.0) vs localhost only; requires firewall allow on Windows.
    "transfer_hub_allow_lan": False,
}


def _settings_for_storage(d: dict) -> dict:
    """Strip keys that cannot be JSON-serialized (e.g. PIL.Image in current_img)."""
    return {k: v for k, v in d.items() if k != "current_img"}


class LiveState(dict):
    def __init__(self, engine, key, *args, **kwargs):
        self._engine = engine
        self._db_key = key
        self.batch_mode = False
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        # 1. Update the local dictionary value
        super().__setitem__(key, value)
        # 2. If not in batch mode, sync the whole dictionary to LMDB
        if not self.batch_mode:
            self.flush()

    # Sync the whole dictionary to LMDB
    def flush(self):
        self._engine.write(self._db_key, _settings_for_storage(dict(self)))

    def begin_batch(self):
        self.batch_mode = True

    def commit(self):
        self.batch_mode = False
        self.flush()


class StorageEngine:
    def __init__(self, env_path: str = "./storage", map_size: int = 10 * 1024 * 1024):
        # 1. Initialize the Environment
        # map_size is the maximum disk space allocated (e.g., 10MB)
        self.lmdb_env = lmdb.open(env_path, map_size=map_size)

    def write(self, key, value):
        # Data must be bytes. We serialize the value to JSON.
        serialized_value = json.dumps(value).encode("utf-8")

        with self.lmdb_env.begin(write=True) as txn:
            txn.put(key.encode("utf-8"), serialized_value)

    def read(self, key, default=None):
        with self.lmdb_env.begin() as txn:
            raw_data = txn.get(key.encode("utf-8"))
            if raw_data is None:
                return default
            return json.loads(raw_data.decode("utf-8"))

    def bind(self, key, default_state):
        raw_state = self.read(key)
        if raw_state is None:
            self.write(key, _settings_for_storage(default_state))
            raw_state = default_state.copy()
        else:
            merged = default_state.copy()
            merged.update(raw_state)
            raw_state = merged
        # In-memory only; never restore a PIL image from LMDB.
        raw_state["current_img"] = None
        state = LiveState(self, key, raw_state)
        return state
