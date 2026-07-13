
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
        'profile',
        required=True,
        encrypted=False,
        default='standard',
        validator=validator.Pattern(
            regex=r"""^(low|standard|high|custom)$""", 
        )
    ), 
    field.RestField(
        'download_mb',
        required=False,
        encrypted=False,
        default='25',
        validator=validator.Number(
            max_val=500, 
            min_val=1, 
            is_int=True, 
        )
    ), 
    field.RestField(
        'upload_mb',
        required=False,
        encrypted=False,
        default='5',
        validator=validator.Number(
            max_val=100, 
            min_val=1, 
            is_int=True, 
        )
    ), 
    field.RestField(
        'interval',
        required=True,
        encrypted=False,
        default='1800',
        validator=validator.Number(
            max_val=86400, 
            min_val=300, 
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
    'speedtest_probe',
    model,
)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=AdminExternalHandler,
    )
