"""The single API definition is a valid OpenAPI 3.1 document."""

import pytest
from openapi_spec_validator import OpenAPIV31SpecValidator, validate
from openapi_spec_validator.readers import read_from_filename
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from tests import constants as test_constants

SPEC_PATH = test_constants.REPOSITORY_ROOT / test_constants.PATH_OPENAPI_SPEC


def test_openapi_document_is_valid_openapi_3_1():
    spec, base_uri = read_from_filename(str(SPEC_PATH))
    validate(spec, base_uri=base_uri, cls=OpenAPIV31SpecValidator)


def test_validator_rejects_a_document_without_its_required_info():
    spec, base_uri = read_from_filename(str(SPEC_PATH))
    broken = {
        key: value for key, value in spec.items() if key != test_constants.SPEC_REQUIRED_SECTION
    }
    with pytest.raises(OpenAPIValidationError):
        validate(broken, base_uri=base_uri, cls=OpenAPIV31SpecValidator)
