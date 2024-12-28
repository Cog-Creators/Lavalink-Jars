#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "packaging",
#   "ruamel.yaml==0.18.6",
#   "urllib3",
# ]
# ///

import argparse
import dataclasses
import json
import enum
import re
from pathlib import Path
from typing import Any, NoReturn, Self

import urllib3
from packaging.specifiers import SpecifierSet
from ruamel.yaml import YAML


http = urllib3.PoolManager()
yaml = YAML(typ="safe")
_LAVALINK_VERSION_PATTERN = re.compile(
    rb"""
    ^
    (?P<version>
        (?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)
        (?:-rc\.(?P<rc>0|[1-9]\d*))?
        # additional build metadata, can be used by our downstream Lavalink
        # if we need to alter an upstream release
        (?:\+red\.(?P<red>[1-9]\d*))?
    )
    $
    """,
    re.MULTILINE | re.VERBOSE,
)
_RELEASES_YAML = Path(__file__).absolute().parent / "releases.yaml"
_RED_JARS_REPO = "https://github.com/Cog-Creators/Lavalink-Jars"
_DEFAULT_PLUGIN_REPOSITORY = "https://maven.lavalink.dev/releases"


@dataclasses.dataclass()
class Plugin:
    group: str
    name: str
    version: str
    repository: str

    @property
    def url(self) -> str:
        return (
            f"{self.repository}/{self.group.replace('.', '/')}"
            f"/{self.name}/{self.version}/{self.name}-{self.version}.jar"
        )


def _raise_type_error(release_name: str, msg: str) -> NoReturn:
    raise TypeError(f"For {release_name!r} release: {msg}")


class ReleaseStream(enum.Enum):
    STABLE = "stable"
    PREVIEW = "preview"


@dataclasses.dataclass()
class ReleaseInfo:
    release_name: str
    jar_version: str
    jar_url: str
    yt_plugin: Plugin
    java_versions: tuple[int, ...]
    release_stream: ReleaseStream
    # inclusive
    min_red_version: str
    # exclusive
    max_red_version: str = ""
    application_yml_overrides: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def parse(cls, release_name: Any, data: Any) -> Self:
        if not isinstance(release_name, str):
            raise TypeError(f"expected release name to be a string, got {release_name!r} instead")
        if not isinstance(data, dict):
            _raise_type_error(release_name, "expected release info to be a dictionary")

        jar_version = cls._parse_jar_version(release_name, data)
        jar_url = cls._get_jar_url(release_name, jar_version)
        yt_plugin = cls._parse_yt_plugin(release_name, data)
        java_versions = cls._parse_java_versions(release_name, data)
        min_red_version = cls._parse_min_red_version(release_name, data)
        release_stream = cls._parse_release_stream(release_name, data)
        application_yml_overrides = cls._parse_application_yml_overrides(release_name, data)

        return cls(
            release_name=release_name,
            jar_version=jar_version,
            jar_url=jar_url,
            yt_plugin=yt_plugin,
            java_versions=java_versions,
            release_stream=release_stream,
            min_red_version=min_red_version,
            application_yml_overrides=application_yml_overrides,
        )

    @property
    def red_version(self) -> SpecifierSet:
        specifiers = SpecifierSet(f">={self.min_red_version}")
        if self.max_red_version:
            specifiers &= SpecifierSet(f"<{self.max_red_version}")
        return specifiers

    def as_json_dict(self) -> dict[str, Any]:
        return {
            "release_name": self.release_name,
            "jar_version": self.jar_version,
            "jar_url": self.jar_url,
            "yt_plugin_version": self.yt_plugin.version,
            "java_versions": list(self.java_versions),
            "red_version": str(self.red_version),
            "release_stream": self.release_stream.value,
            "application_yml_overrides": self.application_yml_overrides,
        }

    @staticmethod
    def _parse_jar_version(release_name: str, data: dict[Any, Any]) -> str:
        try:
            jar_version = data["jar_version"]
        except KeyError:
            _raise_type_error(release_name, "expected jar_version to be set")
        if not isinstance(jar_version, str):
            _raise_type_error(release_name, "expected jar_version to be a string")
        return jar_version

    @staticmethod
    def _get_jar_url(release_name: str, jar_version: str) -> str:
        jar_url = f"{_RED_JARS_REPO}/releases/download/{jar_version}/Lavalink.jar"
        resp = http.request("HEAD", jar_url)
        if resp.status >= 400:
            _raise_type_error(
                release_name, f"expected Lavalink.jar to be available at: {jar_url}"
            )
        return jar_url

    @staticmethod
    def _parse_yt_plugin(release_name: str, data: dict[Any, Any]) -> Plugin:
        try:
            yt_plugin_version = data["yt_plugin_version"]
        except KeyError:
            _raise_type_error(release_name, "expected yt_plugin_version to be set")
        if not isinstance(yt_plugin_version, str):
            _raise_type_error(release_name, "expected yt_plugin_version to be a string")
        yt_plugin = Plugin(
            group="dev.lavalink.youtube",
            name="youtube-plugin",
            version=yt_plugin_version,
            repository=_DEFAULT_PLUGIN_REPOSITORY,
        )
        resp = http.request("HEAD", yt_plugin.url)
        if resp.status >= 400:
            _raise_type_error(
                release_name, f"expected YT plugin to be available at: {yt_plugin.url}"
            )
        return yt_plugin

    @staticmethod
    def _parse_java_versions(release_name: str, data: dict[Any, Any]) -> tuple[int, ...]:
        try:
            java_versions = data["java_versions"]
        except KeyError:
            _raise_type_error(release_name, "expected java_versions to be set")
        if not (
            isinstance(java_versions, list)
            and all(isinstance(x, int) for x in java_versions)
        ):
            _raise_type_error(
                release_name, "expected java_versions to be a list of version numbers (integers)"
            )
        return tuple(java_versions)

    @staticmethod
    def _parse_min_red_version(release_name: str, data: dict[Any, Any]) -> str:
        try:
            min_red_version = data["min_red_version"]
        except KeyError:
            _raise_type_error(release_name, "expected min_red_version to be set")
        if not isinstance(min_red_version, str):
            _raise_type_error(release_name, "expected min_red_version to be a string")
        return min_red_version

    @staticmethod
    def _parse_release_stream(release_name: str, data: dict[Any, Any]) -> ReleaseStream:
        try:
            raw_release_stream = data["release_stream"]
        except KeyError:
            _raise_type_error(release_name, "expected release_stream to be set")
        if not isinstance(raw_release_stream, str):
            _raise_type_error(release_name,  "expected release_stream to be a string")
        try:
            release_stream = ReleaseStream(raw_release_stream)
        except ValueError:
            _raise_type_error(
                release_name,
                (
                    "expected release_stream to be one of: "
                    + ", ".join(member.value for member in ReleaseStream)
                ),
            )
        return release_stream

    @staticmethod
    def _parse_application_yml_overrides(
        release_name: str, data: dict[Any, Any]
    ) -> dict[str, Any]:
        overrides = data.get("application_yml_overrides", {})
        if not isinstance(overrides, dict):
            _raise_type_error(
                release_name,  "expected application_yml_overrides to be a dictionary"
            )
        return overrides


def parse_releases() -> list[ReleaseInfo]:
    with open(_RELEASES_YAML, encoding="utf-8") as fp:
        data = yaml.load(fp)

    if not isinstance(data, dict):
        raise TypeError("expected top-level object in the YAML file to be a dictionary")
    try:
        releases = data["releases"]
    except KeyError:
        raise TypeError("expected releases to be set")

    errors = []
    parsed_releases = []
    previous_release: ReleaseInfo | None = None

    for name, release_data in releases.items():
        print(f"Processing {name!r}...")
        try:
            info = ReleaseInfo.parse(name, release_data)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if previous_release is not None:
            if previous_release.min_red_version != info.min_red_version:
                info.max_red_version = previous_release.min_red_version
            else:
                info.max_red_version = previous_release.max_red_version
        parsed_releases.append(info)
        previous_release = info

    if errors:
        raise ValueError("\n".join(f"- {err}" for err in errors))

    return parsed_releases


def generate_index(releases: list[ReleaseInfo], output_dir: Path) -> None:
    output = [release.as_json_dict() for release in releases]
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "index.0.json", "w", encoding="utf-8") as fp:
        json.dump(output, fp, indent=4)
    with open(output_dir / "index.0-min.json", "w", encoding="utf-8") as fp:
        json.dump(output, fp, separators=(",", ":"))


def generate_index_cmd(args: argparse.Namespace) -> None:
    releases = parse_releases()
    generate_index(releases, Path(args.output_dir))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="available commands")

    generate_index = subparsers.add_parser("generate-index")
    generate_index.add_argument("output_dir", help="The directory to output the index files to.")
    generate_index.set_defaults(func=generate_index_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
