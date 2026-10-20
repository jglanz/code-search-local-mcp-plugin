"""Generate the service API models from the OpenAPI document; also the Hatch build hook.

``packages/code-search-local-api/openapi.yaml`` is the only definition of the HTTP API.
Every wheel and editable build, and ``hatch run generate``, turns it into pydantic models
and a JSON copy of the document inside ``code_search_local/api``. Both outputs are
git-ignored build artifacts. Release wheels additionally bundle the built web dashboard
when ``packages/code-search-local-webapp/dist`` exists, and sdists carry that build so a
wheel rebuilt from the sdist bundles it too.
"""

import json
import os
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# This module lives at <repository>/packages/code-search-local/scripts/api_models.py.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = Path("packages/code-search-local-api/openapi.yaml")
API_PACKAGE_PATH = Path("packages/code-search-local/src/code_search_local/api")
WEBAPP_DIST_PATH = Path("packages/code-search-local-webapp/dist")
WHEEL_API_DIRECTORY = "code_search_local/api"
WHEEL_WEBAPP_DIRECTORY = "code_search_local/assets/webapp"
MODELS_FILENAME = "models.py"
DOCUMENT_FILENAME = "openapi.json"
WEBAPP_INDEX_FILENAME = "index.html"
TEMPORARY_FILENAME_TEMPLATE = ".{name}.{pid}.tmp"
TARGET_SDIST = "sdist"
VERSION_EDITABLE = "editable"
BUILD_DATA_FORCE_INCLUDE = "force_include"
TEXT_ENCODING = "utf-8"
JSON_INDENT = 2


def write_if_changed(path, content):
    """Replace ``path`` atomically, leaving it untouched when the content is unchanged."""
    if path.is_file() and path.read_text(encoding=TEXT_ENCODING) == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(TEMPORARY_FILENAME_TEMPLATE.format(name=path.name, pid=os.getpid()))
    temporary.write_text(content, encoding=TEXT_ENCODING)
    os.replace(temporary, path)


def generate_api_models(spec_path, output_directory):
    """Write the JSON document and its pydantic models for ``spec_path``; return both paths.

    Output depends only on the document and the pinned generator: the built-in formatter
    and the omitted timestamp make repeated runs byte-identical.
    """
    import yaml
    from datamodel_code_generator import (
        DataModelType,
        Formatter,
        InputFileType,
        PythonVersion,
        generate,
    )

    document = (
        json.dumps(yaml.safe_load(spec_path.read_text(encoding=TEXT_ENCODING)), indent=JSON_INDENT)
        + "\n"
    )
    models = generate(
        document,
        input_file_type=InputFileType.OpenAPI,
        input_filename=spec_path.name,
        output_model_type=DataModelType.PydanticV2BaseModel,
        use_annotated=True,
        field_constraints=True,
        use_standard_collections=True,
        use_union_operator=True,
        target_python_version=PythonVersion.PY_312,
        strict_nullable=True,
        disable_timestamp=True,
        formatters=[Formatter.BUILTIN],
    )
    outputs = {
        output_directory / DOCUMENT_FILENAME: document,
        output_directory / MODELS_FILENAME: models,
    }
    for path, content in outputs.items():
        write_if_changed(path, content)
    return list(outputs)


class ApiModelsBuildHook(BuildHookInterface):
    """Generate the API models for wheels and bundle build outputs into artifacts."""

    def initialize(self, version, build_data):
        root = Path(self.root)
        force_include = build_data[BUILD_DATA_FORCE_INCLUDE]
        webapp = root / WEBAPP_DIST_PATH
        webapp_built = (webapp / WEBAPP_INDEX_FILENAME).is_file()
        if self.target_name == TARGET_SDIST:
            # Sources only: the generated models are rebuilt from the bundled document.
            if webapp_built:
                force_include[str(webapp)] = WEBAPP_DIST_PATH.as_posix()
            return
        generated = generate_api_models(root / SPEC_PATH, root / API_PACKAGE_PATH)
        if version == VERSION_EDITABLE:
            # Editable installs import the generated files and the checkout build in place.
            return
        for path in generated:
            force_include[str(path)] = f"{WHEEL_API_DIRECTORY}/{path.name}"
        if webapp_built:
            force_include[str(webapp)] = WHEEL_WEBAPP_DIRECTORY


def main():
    """Regenerate the checkout's API models, as builds do."""
    for path in generate_api_models(
        REPOSITORY_ROOT / SPEC_PATH, REPOSITORY_ROOT / API_PACKAGE_PATH
    ):
        print(f"Generated {path.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
