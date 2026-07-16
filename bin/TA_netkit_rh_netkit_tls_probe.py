
import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    DataInputModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
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
        'targets',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.Pattern(
            regex=r"""^[ \t]*[A-Za-z0-9._:-]+(:\d{1,5})?([ \t]*,[ \t]*[A-Za-z0-9._:-]+(:\d{1,5})?)*[ \t]*$""", 
        )
    ), 
    field.RestField(
        'timeout_ms',
        required=False,
        encrypted=False,
        default='5000',
        validator=validator.Number(
            max_val=60000, 
            min_val=1, 
            is_int=True, 
        )
    ), 
    field.RestField(
        'ca',
        required=False,
        encrypted=False,
        default=None,
        validator=None
    ), 
    field.RestField(
        'interval',
        required=True,
        encrypted=False,
        default='3600',
        validator=validator.Number(
            max_val=86400, 
            min_val=10, 
            is_int=True, 
        )
    ), 
    field.RestField(
        'index',
        required=False,
        encrypted=False,
        default='default',
        validator=validator.IndexName()
    ), 

    field.RestField(
        'disabled',
        required=False,
        validator=None
    )

]
model = RestModel(fields, name=None, special_fields=special_fields)



endpoint = DataInputModel(
    'netkit_tls_probe',
    model,
)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=AdminExternalHandler,
    )
