try:
    import import_declare_test
except ImportError:
    pass

import netkit_ca
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from splunktaucclib.rest_handler.error import RestError


class CertificateAuthorityHandler(AdminExternalHandler):
    def _validate(self):
        try:
            netkit_ca.validate_ca_certificate(self.payload.get("ca_certificate", ""))
        except ValueError as exc:
            raise RestError(400, str(exc))

    def handleCreate(self, confInfo):
        self._validate()
        AdminExternalHandler.handleCreate(self, confInfo)

    def handleEdit(self, confInfo):
        self._validate()
        AdminExternalHandler.handleEdit(self, confInfo)
