"""Gemensamma testfakes: efterliknar Creator- och skill-RPC:erna per användare."""

import re
import uuid

from connect_service import skills as sk
from connect_service.data import ConnectWriteError

TOKEN = "test-access-token"


class _BaseLibrary:
    """Efterliknar Creator-RPC:erna: privata prompter per användare, idempotens per request_id."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.writes: list[str] = []
        self._seen: dict[str, dict[str, object]] = {}

    def list_connect_documents(self, *, access_token, categories):
        assert access_token == TOKEN
        return [dict(row) for row in self.rows.values() if row["category"] in categories and row["status"] != "archived"]

    def create_my_prompt(self, *, access_token, title, content, summary, category, request_id):
        if request_id in self._seen:
            return self._seen[request_id]
        prompt_id = str(uuid.uuid4())
        self.rows[prompt_id] = {"id": prompt_id, "title": title, "content": content, "summary": summary, "category": category, "status": "draft", "updated_at": f"{len(self.writes):04d}"}
        self.writes.append("create")
        self._seen[request_id] = {"id": prompt_id}
        return self._seen[request_id]

    def update_my_prompt(self, *, access_token, prompt_id, title, content, summary, category, request_id):
        if request_id in self._seen:
            return self._seen[request_id]
        row = self.rows[prompt_id]
        row.update({"title": title, "content": content, "summary": summary, "category": category, "updated_at": f"{len(self.writes):04d}"})
        self.writes.append("update")
        self._seen[request_id] = {"id": prompt_id}
        return self._seen[request_id]

    def archive_my_prompt(self, *, access_token, prompt_id, request_id):
        self.rows[prompt_id]["status"] = "archived"
        self.writes.append("archive")
        return {"id": prompt_id, "status": "archived"}

    def get_open_item(self, *, access_token, kind, ref):
        if kind == "package" and ref == "superplanlage":
            return {"kind": "package", "slug": ref, "steps": [{"position": 1, "title": "Riktning", "prompt_text": "Fas 1"}]}
        return None



REQUIRED = ("name", "description", "use_when", "not_when", "instructions")
PATH = re.compile(r"^(references|assets)/[a-z0-9][a-z0-9._-]{0,79}\.(md|txt|csv|json)$")


def rid() -> str:
    return str(uuid.uuid4())


def _slug(name: str) -> str:
    table = str.maketrans("åäöÅÄÖ", "aaoaao")
    return re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")[:64]


def _render(spec, version):
    return f"---\nname: {spec['slug']}\nmetadata:\n  version: \"1.{version - 1}.0\"\n---\n\n# {spec['name']}\n\n{spec['instructions']}\n" + "".join(
        f"{n}. {step}\n" for n, step in enumerate(spec.get("steps", []), 1)
    ) + "".join(f"- {rule}\n" for rule in spec.get("quality_rules", []))


def _slug(name: str) -> str:
    table = str.maketrans("åäöÅÄÖ", "aaoaao")
    return re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")[:64]


def _render(spec, version):
    return f"---\nname: {spec['slug']}\nmetadata:\n  version: \"1.{version - 1}.0\"\n---\n\n# {spec['name']}\n\n{spec['instructions']}\n" + "".join(
        f"{n}. {step}\n" for n, step in enumerate(spec.get("steps", []), 1)
    ) + "".join(f"- {rule}\n" for rule in spec.get("quality_rules", []))



class _SkillLibrary(_BaseLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.skills: dict[str, dict] = {}
        self.versions: dict[tuple[str, int], dict] = {}
        self.skill_requests: dict[tuple[str, str, str], dict] = {}
        self.skill_writes: list[str] = []

    # --- läsning

    def list_my_skills(self, *, access_token):
        return [
            {
                "id": row["id"],
                "slug": row["spec"]["slug"],
                "name": row["spec"]["name"],
                "description": row["spec"]["description"],
                "use_when": row["spec"]["use_when"],
                "not_when": row["spec"]["not_when"],
                "language": "sv",
                "version": row["version"],
                "is_active": row["active"],
                "status": "draft",
                "file_count": len(row["spec"].get("files", [])),
                "extends": row["spec"].get("extends"),
                "updated_at": f"{row['version']:04d}",
            }
            for row in self.skills.values()
            if row["owner"] == access_token
        ]

    def _find(self, token, skill_id, slug):
        for row in self.skills.values():
            if row["owner"] == token and (row["id"] == skill_id or (skill_id is None and row["spec"]["slug"] == slug)):
                return row
        return None

    def get_my_skill(self, *, access_token, skill_id=None, slug=None, version=None, file_path=None, include_files=True):
        row = self._find(access_token, skill_id, slug)
        if row is None:
            return None
        v = version or row["version"]
        snap = self.versions.get((row["id"], v))
        if snap is None:
            return None
        spec = snap["spec"]
        if file_path is not None:
            match = next((f for f in spec.get("files", []) if f["path"] == file_path), None)
            return None if match is None else {"id": row["id"], "slug": spec["slug"], "version": v, "path": match["path"], "content": match["content"]}
        files = [{"path": f["path"], "chars": len(f["content"]), **({"content": f["content"]} if include_files else {})} for f in spec.get("files", [])]
        return {
            "id": row["id"], **{k: spec.get(k) for k in ("slug", "name", "description", "use_when", "not_when", "instructions", "language", "extends")},
            "steps": spec.get("steps", []), "quality_rules": spec.get("quality_rules", []), "dependencies": spec.get("dependencies", []),
            "version": v, "current_version": row["version"], "is_active": row["active"], "status": "draft",
            "skill_md": snap["skill_md"], "files": files,
        }

    def list_my_skill_versions(self, *, access_token, skill_id):
        row = self._find(access_token, skill_id, None)
        assert row is not None
        return [{"version": v, "note": s["note"], "is_current": v == row["version"]} for (sid, v), s in sorted(self.versions.items(), reverse=True) if sid == skill_id]

    def validate_my_skill(self, *, access_token, spec, skill_id=None):
        errors = [f"{key} krävs." for key in REQUIRED if not str(spec.get(key) or "").strip()]
        errors += [f"Okänt fält: {key}." for key in spec if key not in sk.SPEC_FIELDS]
        paths = []
        for item in spec.get("files", []) or []:
            if not PATH.match(item.get("path", "")) or ".." in item.get("path", ""):
                errors.append(f"Ogiltig sökväg: {item.get('path')}.")
            paths.append(item.get("path"))
        for ref in re.findall(r"(?:references|assets)/[A-Za-z0-9._/-]+[A-Za-z0-9]", str(spec.get("instructions", ""))):
            if ref not in paths:
                errors.append(f"Instruktionen hänvisar till {ref}, som inte finns bland filerna.")
        version = 1
        fixed = None
        if skill_id is not None:
            row = self._find(access_token, skill_id, None)
            if row is None:
                raise ConnectWriteError("Skillen hittades inte eller tillhör inte dig.", kind="validation")
            fixed, version = row["spec"]["slug"], row["version"] + 1
        normalized = {k: v for k, v in spec.items() if v not in (None, [], "")}
        normalized["slug"] = fixed or _slug(str(spec.get("slug") or spec.get("name") or ""))
        normalized.setdefault("language", "sv")
        if skill_id is None and any(r["owner"] == access_token and r["spec"]["slug"] == normalized["slug"] for r in self.skills.values()):
            errors.append("Du har redan en skill med samma id.")
        return {"valid": not errors, "errors": errors, "slug": normalized["slug"], "version": version, "spec": normalized,
                "skill_md": None if errors else _render(normalized, version)}

    # --- skrivning

    def _replay(self, token, tool, request_id):
        return self.skill_requests.get((token, tool, request_id))

    def create_my_skill(self, *, access_token, spec, request_id):
        if (prev := self._replay(access_token, "create", request_id)) is not None:
            return prev
        check = self.validate_my_skill(access_token=access_token, spec=spec)
        if not check["valid"]:
            raise ConnectWriteError(" ".join(check["errors"]), kind="validation")
        if sum(1 for r in self.skills.values() if r["owner"] == access_token) >= 5:
            raise ConnectWriteError("Du har nått gränsen på 5 egna skills för free-planen.", kind="quota")
        skill_id = str(uuid.uuid4())
        self.skills[skill_id] = {"id": skill_id, "owner": access_token, "spec": check["spec"], "version": 1, "active": True}
        self.versions[(skill_id, 1)] = {"spec": check["spec"], "skill_md": check["skill_md"], "note": None}
        result = {"id": skill_id, "slug": check["slug"], "version": 1}
        self.skill_requests[(access_token, "create", request_id)] = result
        self.skill_writes.append("create")
        return result

    def update_my_skill(self, *, access_token, skill_id, spec, expected_version, note, request_id):
        if (prev := self._replay(access_token, "update", request_id)) is not None:
            return prev
        row = self._find(access_token, skill_id, None)
        if row is None:
            raise ConnectWriteError("Skillen hittades inte eller tillhör inte dig.", kind="validation")
        if row["version"] != expected_version:
            raise ConnectWriteError(f"Versionskonflikt: skillen är nu version {row['version']}.", kind="conflict")
        check = self.validate_my_skill(access_token=access_token, spec=spec, skill_id=skill_id)
        new = row["version"] + 1
        row.update(spec=check["spec"], version=new)
        self.versions[(skill_id, new)] = {"spec": check["spec"], "skill_md": check["skill_md"], "note": note}
        result = {"id": skill_id, "version": new}
        self.skill_requests[(access_token, "update", request_id)] = result
        self.skill_writes.append("update")
        return result

    def set_my_skill_active(self, *, access_token, skill_id, active, request_id):
        row = self._find(access_token, skill_id, None)
        assert row is not None
        row["active"] = active
        self.skill_writes.append("active")
        return {"id": skill_id, "is_active": active}



class MemoryLibrary(_SkillLibrary):
    def __init__(self) -> None:
        _SkillLibrary.__init__(self)
        self.submissions: list[dict] = []
        self.published: dict[str, dict] = {}

    def submit_to_promptbanken(self, *, access_token, kind, product_id, consent_distribution, rights_attested, request_id):
        skill_id = product_id
        row = self._find(access_token, skill_id, None)
        assert row is not None
        if any(s["skill_id"] == skill_id and s["state"] == "review" for s in self.submissions):
            raise ConnectWriteError("Det finns redan en version under granskning.", kind="validation")
        sub = {
            "submission_id": str(uuid.uuid4()), "kind": kind, "product_id": skill_id, "skill_id": skill_id, "slug": row["spec"]["slug"], "name": row["spec"]["name"],
            "version": row["version"], "revision": 1, "state": "review", "review_note": None, "owner": access_token,
            "catalog_slug": None, "catalog_status": None, "catalog_published_version": None,
        }
        self.submissions.append(sub)
        self.skill_writes.append("submit")
        return {"id": sub["submission_id"], "status": "review", "version": row["version"], "revision": 1}

    def list_my_submissions(self, *, access_token, kind=None, product_id=None):
        return [dict(s) for s in self.submissions if s["owner"] == access_token and (product_id is None or s["product_id"] == product_id) and (kind is None or s["kind"] == kind)]

    def withdraw_my_submission(self, *, access_token, submission_id, request_id):
        for s in self.submissions:
            if s["submission_id"] == submission_id and s["owner"] == access_token:
                s["state"] = "withdrawn"
                return {"id": submission_id, "status": "withdrawn"}
        raise ConnectWriteError("Inskicket hittades inte.", kind="validation")

    def list_published_skills(self, *, access_token):
        return [
            {"slug": slug, "name": p["name"], "description": "d", "use_when": "u", "not_when": "n", "version": p["version"],
             "distribution_allowed": p["distribution"], "creator_display_name": "Testskapare"}
            for slug, p in self.published.items()
        ]

    def get_published_skill(self, *, access_token, slug, version=None, file_path=None):
        p = self.published.get(slug)
        if p is None:
            return None
        if file_path is not None:
            if file_path != "references/checklista.md":
                return None
            return {"slug": slug, "version": p["version"], "path": file_path, "content": "- Pris"}
        return {
            "slug": slug, "name": p["name"], "version": p["version"], "skill_md": "---\nname: " + slug + "\n---\n# " + p["name"],
            "files": [{"path": "references/checklista.md", "content": "- Pris"}], "distribution_allowed": p["distribution"],
            "creator_display_name": "Testskapare",
        }


