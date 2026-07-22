from __future__ import annotations

from pathlib import Path

import yaml

from .devtools import DevToolsConfig


DEFAULT_PROFILE_NAME = "dgx-01"
DEFAULT_CONFIG = DevToolsConfig(
    backend_host="192.168.0.220",
    backend_port=8000,
    ssh_target="gblab-dgx-01",
    chrome_debug_port=9333,
    remote_debug_port=9222,
    chrome_profile="",
)


def validate_profile_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("프로파일 이름을 입력하세요.")
    if len(name) > 64 or any(character in name for character in "\r\n"):
        raise ValueError("프로파일 이름은 한 줄, 64자 이내여야 합니다.")
    return name


class ProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.active_profile = DEFAULT_PROFILE_NAME
        self.profiles: dict[str, DevToolsConfig] = {}

    def load(self) -> None:
        if not self.path.exists():
            self.profiles = {DEFAULT_PROFILE_NAME: DEFAULT_CONFIG}
            self.active_profile = DEFAULT_PROFILE_NAME
            self.write()
            return

        payload = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"YAML 최상위 값은 mapping이어야 합니다: {self.path}")
        raw_profiles = payload.get("profiles")
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ValueError("profiles에는 하나 이상의 프로파일이 필요합니다.")

        loaded: dict[str, DevToolsConfig] = {}
        for raw_name, raw_config in raw_profiles.items():
            name = validate_profile_name(str(raw_name))
            if not isinstance(raw_config, dict):
                raise ValueError(f"프로파일 '{name}' 설정은 mapping이어야 합니다.")
            loaded[name] = DevToolsConfig.from_mapping(raw_config)

        active = str(payload.get("active_profile", "")).strip()
        self.profiles = loaded
        self.active_profile = active if active in loaded else next(iter(loaded))

    def write(self) -> None:
        payload = {
            "version": 1,
            "active_profile": self.active_profile,
            "profiles": {
                name: config.to_mapping() for name, config in self.profiles.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def save_profile(self, name: str, config: DevToolsConfig) -> None:
        name = validate_profile_name(name)
        self.profiles[name] = config
        self.active_profile = name
        self.write()

    def set_active(self, name: str) -> None:
        if name not in self.profiles:
            raise KeyError(name)
        self.active_profile = name
        self.write()

    def delete_profile(self, name: str) -> str:
        if name not in self.profiles:
            raise KeyError(name)
        if len(self.profiles) == 1:
            raise ValueError("마지막 프로파일은 삭제할 수 없습니다.")
        del self.profiles[name]
        self.active_profile = next(iter(self.profiles))
        self.write()
        return self.active_profile
