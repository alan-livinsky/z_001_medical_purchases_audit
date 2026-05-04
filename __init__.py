from trytond.pool import Pool

from . import medical_purchases_audit


def register():
    Pool.register(
        medical_purchases_audit.MedicationPurchasePackage,
        medical_purchases_audit.MedicalPurchaseAudit,
        medical_purchases_audit.MedicalPurchaseAuditLine,
        medical_purchases_audit.CreatePurchaseDraftStart,
        medical_purchases_audit.ReviewPurchaseAuditStart,
        module='z_001_medical_purchases_audit', type_='model')
    Pool.register(
        medical_purchases_audit.CreatePurchaseDraftWizard,
        medical_purchases_audit.ReviewPurchaseAuditWizard,
        module='z_001_medical_purchases_audit', type_='wizard')
