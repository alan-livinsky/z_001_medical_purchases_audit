# SPDX-FileCopyrightText: 2026 Custom GNU Health
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from trytond.exceptions import UserError
from trytond.model import ModelSQL, ModelView, Unique, fields
from trytond.pool import Pool
from trytond.pyson import Bool, Eval, Not
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard

__all__ = [
    'MedicationPurchasePackage',
    'MedicalPurchaseAudit',
    'MedicalPurchaseAuditLine',
    'CreatePurchaseDraftStart',
    'CreatePurchaseDraftWizard',
    'ReviewPurchaseAuditStart',
    'ReviewPurchaseAuditWizard',
]

ZERO = Decimal('0.00')
MONTH_NAMES = {
    1: 'enero',
    2: 'febrero',
    3: 'marzo',
    4: 'abril',
    5: 'mayo',
    6: 'junio',
    7: 'julio',
    8: 'agosto',
    9: 'septiembre',
    10: 'octubre',
    11: 'noviembre',
    12: 'diciembre',
}


class MedicationPurchasePackage(ModelSQL, ModelView):
    'Medication Purchase Package'
    __name__ = 'gnuhealth.medication.purchase.package'

    purchase_drafts = fields.One2Many(
        'gnuhealth.medical.purchase.audit', 'package',
        'Borradores de Compra', readonly=True)
    purchase_draft_count = fields.Function(
        fields.Integer('Cantidad de Borradores'),
        'get_purchase_draft_metrics')
    has_active_purchase_draft = fields.Function(
        fields.Boolean('Tiene Borrador Activo'),
        'get_purchase_draft_metrics')

    @classmethod
    def get_purchase_draft_metrics(cls, records, name):
        result = {}
        for record in records:
            if name == 'purchase_draft_count':
                result[record.id] = len(record.purchase_drafts)
            elif name == 'has_active_purchase_draft':
                result[record.id] = any(
                    draft.state in ('draft', 'signed_by_purchases')
                    for draft in record.purchase_drafts)
            else:
                result[record.id] = None
        return result


class MedicalPurchaseAudit(ModelSQL, ModelView):
    'Medical Purchase Audit'
    __name__ = 'gnuhealth.medical.purchase.audit'

    name = fields.Char('Nombre', readonly=True)
    base_name = fields.Char('Nombre Base', readonly=True)
    package = fields.Many2One(
        'gnuhealth.medication.purchase.package', 'Paquete',
        required=True, readonly=True)
    origin_document = fields.Many2One(
        'gnuhealth.medical.purchase.audit', 'Documento Origen',
        readonly=True)
    origin_document_display = fields.Function(
        fields.Char('Documento Origen'),
        'get_origin_document_display')
    revision_number = fields.Integer('Revision', readonly=True)
    revision_display = fields.Function(
        fields.Char('Revision'),
        'get_revision_display')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('signed_by_purchases', 'Firmado por Compras'),
        ('accepted', 'Aceptado'),
        ('rejected', 'Rechazado'),
    ], 'Estado', readonly=True, sort=False)
    lines = fields.One2Many(
        'gnuhealth.medical.purchase.audit.line', 'document', 'Medicamentos',
        states={'readonly': Not(Bool(Eval('can_edit')))},
        depends=['can_edit'])
    total_amount = fields.Function(
        fields.Numeric('Total', digits=(16, 2)), 'get_total_amount')
    line_count = fields.Function(
        fields.Integer('Cantidad de Lineas'), 'get_line_count')
    can_edit = fields.Function(
        fields.Boolean('Puede Editar'), 'get_can_edit')
    signed_by_purchase_user = fields.Many2One(
        'res.user', 'Firmado por Compras', readonly=True)
    signed_by_purchase_date = fields.DateTime(
        'Fecha Firma Compras', readonly=True)
    auditor_review_user = fields.Many2One(
        'res.user', 'Revisado por Auditor', readonly=True)
    auditor_review_date = fields.DateTime(
        'Fecha Revision Auditor', readonly=True)
    rejection_observation = fields.Text(
        'Observacion de Rechazo', readonly=True)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
            'sign_by_purchases': {
                'invisible': Eval('state') != 'draft',
                'depends': ['state'],
            },
        })

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_revision_number():
        return 0

    @classmethod
    def _current_user_has_group(cls, group_xml_id):
        pool = Pool()
        User = pool.get('res.user')
        ModelData = pool.get('ir.model.data')
        try:
            group_id = ModelData.get_id(
                'z_001_medical_purchases_audit', group_xml_id)
        except KeyError:
            return False
        current_user = User(Transaction().user)
        return any(group.id == group_id for group in current_user.groups)

    @classmethod
    def _current_user_is_purchase_manager(cls):
        return cls._current_user_has_group('z_gestor_compras_medicamentos')

    @classmethod
    def _current_user_is_medical_auditor(cls):
        return cls._current_user_has_group(
            'z_auditor_medico_compras_medicamentos')

    @classmethod
    def _ensure_purchase_manager(cls):
        if not cls._current_user_is_purchase_manager():
            raise UserError(
                'No tiene los permisos necesarios para gestionar '
                'borradores de compras.')

    @classmethod
    def _ensure_medical_auditor(cls):
        if not cls._current_user_is_medical_auditor():
            raise UserError(
                'No tiene los permisos necesarios para auditar compras '
                'de medicamentos.')

    @classmethod
    def get_total_amount(cls, records, name):
        result = {}
        for record in records:
            total = ZERO
            for line in record.lines:
                total += line._calculate_subtotal()
            result[record.id] = total
        return result

    @fields.depends('lines')
    def on_change_with_total_amount(self, name=None):
        total = ZERO
        for line in self.lines or []:
            total += line._calculate_subtotal()
        return total

    @classmethod
    def get_line_count(cls, records, name):
        return {record.id: len(record.lines) for record in records}

    @classmethod
    def get_can_edit(cls, records, name):
        return {record.id: record.state == 'draft' for record in records}

    @classmethod
    def get_origin_document_display(cls, records, name):
        return {
            record.id: (
                record.origin_document.rec_name
                if record.origin_document else 'Original'
            )
            for record in records
        }

    @classmethod
    def get_revision_display(cls, records, name):
        return {
            record.id: (
                'Revision %s' % record.revision_number
                if record.revision_number else 'Sin revisiones'
            )
            for record in records
        }

    @classmethod
    def create(cls, vlist):
        context = Transaction().context
        if not (
                context.get('from_purchase_draft_wizard')
                or context.get('from_purchase_package_automation')
                or context.get('from_purchase_revision_clone')):
            raise UserError(
                'Los borradores de compras solo se pueden crear desde el '
                'flujo autorizado.')

        vlist = [dict(v) for v in vlist]
        for vals in vlist:
            vals.setdefault('revision_number', 0)
            vals.setdefault('state', 'draft')
            base_name = vals.get('base_name')
            revision_number = vals.get('revision_number', 0)
            if not base_name:
                package = None
                if vals.get('package'):
                    package = Pool().get('gnuhealth.medication.purchase.package')(
                        vals['package'])
                base_name = cls._build_base_name(package)
                vals['base_name'] = base_name
            vals['name'] = cls._format_name(base_name, revision_number)
        return super().create(vlist)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        allowed_locked_fields = {
            'state', 'signed_by_purchase_user', 'signed_by_purchase_date',
            'auditor_review_user', 'auditor_review_date',
            'rejection_observation', 'name', 'origin_document',
        }
        sign_fields = {
            'state', 'signed_by_purchase_user', 'signed_by_purchase_date',
        }
        review_fields = {
            'state', 'auditor_review_user', 'auditor_review_date',
            'rejection_observation',
        }
        context = Transaction().context
        for records, values in zip(actions, actions):
            changed = set(values.keys())
            for record in records:
                if record.state != 'draft' and changed - allowed_locked_fields:
                    raise UserError(
                        'El borrador de compras ya no se puede editar.')
                if changed & sign_fields:
                    if changed - sign_fields:
                        raise UserError(
                            'La firma de Compras solo puede modificar los '
                            'campos previstos por el flujo.')
                    if not context.get('from_sign_by_purchases'):
                        raise UserError(
                            'El estado firmado por Compras solo se puede '
                            'asignar desde la accion de firma.')
                    cls._ensure_purchase_manager()
                if changed & review_fields:
                    if changed - review_fields:
                        raise UserError(
                            'La revision del auditor solo puede modificar '
                            'los campos previstos por el flujo.')
                    if not context.get('from_purchase_audit_review'):
                        raise UserError(
                            'La decision del auditor solo se puede aplicar '
                            'desde la auditoria de compras de medicamentos.')
                    cls._ensure_medical_auditor()
        super().write(*args)

    @classmethod
    def delete(cls, records):
        for record in records:
            if record.state != 'draft':
                raise UserError(
                    'Solo se pueden eliminar borradores en estado borrador.')
        super().delete(records)

    @classmethod
    def validate(cls, records):
        super().validate(records)
        for record in records:
            record.check_quantities()

    def check_quantities(self):
        for line in self.lines:
            if line.purchase_quantity < 0:
                raise UserError(
                    'La cantidad a comprar no puede ser menor que cero.')
            if line.purchase_quantity > line.original_quantity:
                raise UserError(
                    'La cantidad a comprar no puede superar la cantidad '
                    'consolidada del medicamento.')

    @classmethod
    def _build_base_name(cls, package):
        if package and package.date:
            month_name = MONTH_NAMES.get(package.date.month, 'mes')
            return 'Compras %s %s' % (month_name, package.date.year)
        now = datetime.utcnow()
        month_name = MONTH_NAMES.get(now.month, 'mes')
        return 'Compras %s %s' % (month_name, now.year)

    @classmethod
    def _format_name(cls, base_name, revision_number):
        if revision_number:
            return '%s - revision %s' % (base_name, revision_number)
        return base_name

    @classmethod
    def _validate_package_can_start(cls, package):
        active = cls.search([
            ('package', '=', package.id),
            ('state', 'in', ['draft', 'signed_by_purchases']),
        ], limit=1)
        if active:
            raise UserError(
                'El paquete ya tiene un borrador de compras activo.')

    @classmethod
    def create_from_package(cls, package):
        cls._validate_package_can_start(package)
        consolidated = OrderedDict()
        for audit_line in package.audit_lines:
            medicament = audit_line.medicament
            if not medicament:
                continue
            data = consolidated.setdefault(medicament.id, {
                'medicament': medicament.id,
                'original_quantity': 0,
                'purchase_quantity': 0,
                'unit_price': None,
                'package_line_count': 0,
            })
            data['original_quantity'] += 1
            data['purchase_quantity'] += 1
            data['package_line_count'] += 1

        if not consolidated:
            raise UserError(
                'El paquete no contiene medicamentos para generar un borrador.')

        with Transaction().set_context(from_purchase_package_automation=True):
            document, = cls.create([{
                'package': package.id,
                'base_name': cls._build_base_name(package),
                'revision_number': 0,
                'lines': [('create', list(consolidated.values()))],
            }])
        return document

    def clone_revision(self):
        Line = Pool().get('gnuhealth.medical.purchase.audit.line')
        with Transaction().set_context(from_purchase_revision_clone=True):
            new_document, = self.__class__.create([{
                'package': self.package.id,
                'base_name': self.base_name,
                'origin_document': self.id,
                'revision_number': self.revision_number + 1,
            }])
        Line.create([{
            'document': new_document.id,
            'medicament': line.medicament.id,
            'original_quantity': line.original_quantity,
            'purchase_quantity': line.purchase_quantity,
            'unit_price': line.unit_price,
            'package_line_count': line.package_line_count,
        } for line in self.lines])
        return new_document

    @classmethod
    @ModelView.button
    def sign_by_purchases(cls, records):
        cls._ensure_purchase_manager()
        current_user = Pool().get('res.user')(Transaction().user)
        for record in records:
            if record.state != 'draft':
                raise UserError(
                    'Solo se pueden firmar documentos en estado borrador.')
            if not record.lines:
                raise UserError(
                    'El borrador debe tener medicamentos antes de firmarse.')
            for line in record.lines:
                if line.unit_price is None:
                    raise UserError(
                        'Todos los medicamentos deben tener precio unitario '
                        'antes de firmar.')
                if line.purchase_quantity < 0 or (
                        line.purchase_quantity > line.original_quantity):
                    raise UserError(
                        'Hay cantidades fuera del rango permitido.')
        with Transaction().set_context(from_sign_by_purchases=True):
            cls.write(records, {
                'state': 'signed_by_purchases',
                'signed_by_purchase_user': current_user.id,
                'signed_by_purchase_date': datetime.utcnow(),
            })

    @classmethod
    def accept_documents(cls, records):
        cls._ensure_medical_auditor()
        current_user = Pool().get('res.user')(Transaction().user)
        for record in records:
            if record.state != 'signed_by_purchases':
                raise UserError(
                    'Solo se pueden aceptar documentos firmados por Compras.')
        with Transaction().set_context(from_purchase_audit_review=True):
            cls.write(records, {
                'state': 'accepted',
                'auditor_review_user': current_user.id,
                'auditor_review_date': datetime.utcnow(),
            })

    @classmethod
    def reject_documents(cls, records, observation):
        if not observation:
            raise UserError(
                'Debe ingresar una observacion para rechazar el borrador.')
        cls._ensure_medical_auditor()
        current_user = Pool().get('res.user')(Transaction().user)
        created = []
        for record in records:
            if record.state != 'signed_by_purchases':
                raise UserError(
                    'Solo se pueden rechazar documentos firmados por Compras.')
            with Transaction().set_context(from_purchase_audit_review=True):
                cls.write([record], {
                    'state': 'rejected',
                    'auditor_review_user': current_user.id,
                    'auditor_review_date': datetime.utcnow(),
                    'rejection_observation': observation,
                })
            created.append(record.clone_revision())
        return created


class MedicalPurchaseAuditLine(ModelSQL, ModelView):
    'Medical Purchase Audit Line'
    __name__ = 'gnuhealth.medical.purchase.audit.line'

    document = fields.Many2One(
        'gnuhealth.medical.purchase.audit', 'Documento',
        required=True, ondelete='CASCADE')
    document_state = fields.Function(
        fields.Selection([
            ('draft', 'Borrador'),
            ('signed_by_purchases', 'Firmado por Compras'),
            ('accepted', 'Aceptado'),
            ('rejected', 'Rechazado'),
        ], 'Estado Documento'),
        'get_document_state')
    medicament = fields.Many2One(
        'gnuhealth.medicament', 'Medicamento',
        required=True, readonly=True)
    original_quantity = fields.Integer(
        'Cantidad Consolidada', readonly=True)
    purchase_quantity = fields.Integer(
        'Cantidad a Comprar',
        states={'readonly': Eval('document_state') != 'draft'},
        depends=['document_state'])
    unit_price = fields.Numeric(
        'Precio Unitario', digits=(16, 2),
        states={'readonly': Eval('document_state') != 'draft'},
        depends=['document_state'])
    line_subtotal = fields.Function(
        fields.Numeric('Subtotal', digits=(16, 2)), 'get_line_subtotal')
    package_line_count = fields.Integer(
        'Cantidad de Lineas del Paquete', readonly=True)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        table = cls.__table__()
        cls._sql_constraints = [
            ('document_medicament_unique',
             Unique(table, table.document, table.medicament),
             'Cada medicamento solo puede aparecer una vez por borrador.'),
        ]

    @staticmethod
    def default_purchase_quantity():
        return 0

    @classmethod
    def get_document_state(cls, records, name):
        return {
            record.id: record.document.state if record.document else None
            for record in records
        }

    def _calculate_subtotal(self):
        quantity = Decimal(str(self.purchase_quantity or 0))
        price = self.unit_price if self.unit_price is not None else ZERO
        return price * quantity

    @classmethod
    def get_line_subtotal(cls, records, name):
        return {record.id: record._calculate_subtotal() for record in records}

    @fields.depends('purchase_quantity', 'unit_price')
    def on_change_with_line_subtotal(self, name=None):
        return self._calculate_subtotal()

    @classmethod
    def create(cls, vlist):
        cls._ensure_documents_editable(vlist)
        return super().create(vlist)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        for records, values in zip(actions, actions):
            for record in records:
                if record.document and record.document.state != 'draft':
                    raise UserError(
                        'No se pueden editar lineas de un documento cerrado.')
                purchase_quantity = values.get('purchase_quantity')
                if purchase_quantity is not None:
                    if purchase_quantity < 0:
                        raise UserError(
                            'La cantidad a comprar no puede ser menor que cero.')
                    if purchase_quantity > record.original_quantity:
                        raise UserError(
                            'La cantidad a comprar no puede superar la '
                            'cantidad consolidada.')
        super().write(*args)

    @classmethod
    def delete(cls, records):
        for record in records:
            if record.document and record.document.state != 'draft':
                raise UserError(
                    'No se pueden eliminar lineas de un documento cerrado.')
        super().delete(records)

    @classmethod
    def validate(cls, records):
        super().validate(records)
        for record in records:
            if record.purchase_quantity < 0:
                raise UserError(
                    'La cantidad a comprar no puede ser menor que cero.')
            if record.purchase_quantity > record.original_quantity:
                raise UserError(
                    'La cantidad a comprar no puede superar la cantidad '
                    'consolidada.')

    @classmethod
    def _ensure_documents_editable(cls, vlist):
        Document = Pool().get('gnuhealth.medical.purchase.audit')
        for values in vlist:
            document_id = values.get('document')
            if not document_id:
                continue
            document = Document(document_id)
            if document.state != 'draft':
                raise UserError(
                    'No se pueden agregar lineas a un documento cerrado.')


class CreatePurchaseDraftStart(ModelView):
    'Create Purchase Draft Start'
    __name__ = 'gnuhealth.medical.purchase.audit.create.start'

    package = fields.Many2One(
        'gnuhealth.medication.purchase.package', 'Paquete', readonly=True)
    generated_name = fields.Char('Nombre Generado', readonly=True)

    @classmethod
    def default_package(cls):
        context = Transaction().context
        active_id = context.get('active_id')
        if active_id:
            return active_id

    @classmethod
    def default_generated_name(cls):
        Package = Pool().get('gnuhealth.medication.purchase.package')
        context = Transaction().context
        active_id = context.get('active_id')
        package = Package(active_id) if active_id else None
        return MedicalPurchaseAudit._build_base_name(package)


class CreatePurchaseDraftWizard(Wizard):
    'Create Purchase Draft'
    __name__ = 'gnuhealth.medical.purchase.audit.create'

    start_state = 'start'
    start = StateView(
        'gnuhealth.medical.purchase.audit.create.start',
        'z_001_medical_purchases_audit.view_create_purchase_draft_start',
        [
            Button('Cancelar', 'end', 'tryton-cancel'),
            Button('Confirmar', 'create_draft', 'tryton-ok', default=True),
        ])
    create_draft = StateTransition()

    def transition_create_draft(self):
        Package = Pool().get('gnuhealth.medication.purchase.package')
        MedicalPurchaseAudit._ensure_purchase_manager()
        active_id = Transaction().context.get('active_id')
        if not active_id:
            raise UserError('No se encontro un paquete para procesar.')
        package = Package(active_id)
        with Transaction().set_context(from_purchase_draft_wizard=True):
            MedicalPurchaseAudit.create_from_package(package)
        return 'end'

    def end(self):
        return 'reload'


class ReviewPurchaseAuditStart(ModelView):
    'Review Purchase Audit Start'
    __name__ = 'gnuhealth.medical.purchase.audit.review.start'

    decision = fields.Selection([
        ('accept', 'Aceptar'),
        ('reject', 'Rechazar'),
    ], 'Decision', required=True)
    observation = fields.Text(
        'Observacion',
        states={'readonly': Eval('decision') != 'reject'},
        depends=['decision'])


class ReviewPurchaseAuditWizard(Wizard):
    'Review Purchase Audit'
    __name__ = 'gnuhealth.medical.purchase.audit.review'

    start_state = 'start'
    start = StateView(
        'gnuhealth.medical.purchase.audit.review.start',
        'z_001_medical_purchases_audit.view_review_purchase_audit_start',
        [
            Button('Cancelar', 'end', 'tryton-cancel'),
            Button('Confirmar', 'apply_review', 'tryton-ok', default=True),
        ])
    apply_review = StateTransition()

    def transition_apply_review(self):
        MedicalPurchaseAudit = Pool().get('gnuhealth.medical.purchase.audit')
        MedicalPurchaseAudit._ensure_medical_auditor()
        active_ids = Transaction().context.get('active_ids') or []
        if not active_ids:
            raise UserError('No se selecciono ningun borrador para revisar.')
        records = MedicalPurchaseAudit.browse(active_ids)
        if self.start.decision == 'accept':
            MedicalPurchaseAudit.accept_documents(records)
        elif self.start.decision == 'reject':
            MedicalPurchaseAudit.reject_documents(
                records, self.start.observation)
        else:
            raise UserError('Debe seleccionar una decision valida.')
        return 'end'

    def end(self):
        return 'reload'
