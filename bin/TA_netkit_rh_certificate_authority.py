
import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    SingleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from netkit_ca_handler import CertificateAuthorityHandler
import logging


util.remove_http_proxy_env_vars()


special_fields = [
    field.RestField(
        'name',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.Pattern(
            regex=r"""^[a-zA-Z]\w*$""", 
        )
    )
]

fields = [
    field.RestField(
        'ca_certificate',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=100000, 
            min_len=1, 
        )
    )
]
model = RestModel(fields, name=None, special_fields=special_fields)


endpoint = SingleModel(
    'ta_netkit_certificate_authority',
    model,
    config_name='certificate_authority',
    need_reload=False,
)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=CertificateAuthorityHandler,
    )
