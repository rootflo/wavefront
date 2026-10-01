"""Human-readable presentation for Presidio entity types.

Deliberately imports nothing from Presidio. This module answers "what should we
call ``IN_AADHAAR`` in a settings page", never "can this deployment detect it" -
that second question is answered by asking the running analyzer, because a
catalog that claims an entity the installed recogniser set cannot produce would
offer an admin a checkbox that silently does nothing.

Anything the engine reports but this file does not know about still renders, via
:func:`describe`, as a title-cased id in the ``Other`` group. A Presidio upgrade
that adds recognisers therefore widens the page instead of breaking it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

#: Entities backed by the spaCy NER pipeline rather than a regex.
#:
#: These are context-dependent by nature: they fire on ordinary prose rather
#: than on a checkable identifier shape, so "What's the weather in London on
#: Monday?" yields a LOCATION and a DATE_TIME. Surfaced in the UI as a warning
#: so an admin enabling them knows what they are buying.
NLP_BACKED: frozenset = frozenset(
    {'PERSON', 'LOCATION', 'ORGANIZATION', 'NRP', 'DATE_TIME'}
)

GROUP_GLOBAL = 'Global'
GROUP_OTHER = 'Other'

#: Display order for entity groups. Global first because it is what most
#: deployments actually need; the rest alphabetical. Groups absent from this
#: tuple sort last.
GROUP_ORDER: Tuple[str, ...] = (
    GROUP_GLOBAL,
    'Australia',
    'Canada',
    'Finland',
    'Germany',
    'India',
    'Italy',
    'Nigeria',
    'Philippines',
    'Poland',
    'Singapore',
    'South Africa',
    'South Korea',
    'Spain',
    'Sweden',
    'Thailand',
    'Turkey',
    'United Kingdom',
    'United States',
    GROUP_OTHER,
)


@dataclass(frozen=True)
class EntityMeta:
    """How one entity type is presented in the console."""

    label: str
    description: str
    group: str
    country_code: Optional[str] = None
    example: Optional[str] = None


def _m(
    label: str,
    description: str,
    group: str,
    country_code: Optional[str] = None,
    example: Optional[str] = None,
) -> EntityMeta:
    return EntityMeta(
        label=label,
        description=description,
        group=group,
        country_code=country_code,
        example=example,
    )


ENTITY_CATALOG: Dict[str, EntityMeta] = {
    # -- Global ---------------------------------------------------------
    'CREDIT_CARD': _m(
        'Credit card number',
        'Card numbers from the major networks. Validated with the Luhn '
        'checksum, so ordinary long numbers are not mistaken for cards.',
        GROUP_GLOBAL,
        example='4111 1111 1111 1111',
    ),
    'CRYPTO': _m(
        'Crypto wallet address',
        'Bitcoin and similar wallet addresses.',
        GROUP_GLOBAL,
    ),
    'DATE_TIME': _m(
        'Date or time',
        'Absolute and relative dates. Fires on ordinary business prose, so '
        'enable only when dates are genuinely sensitive.',
        GROUP_GLOBAL,
        example='3rd of June, 2021',
    ),
    'EMAIL_ADDRESS': _m(
        'Email address',
        'Any well-formed email address.',
        GROUP_GLOBAL,
        example='alice@example.com',
    ),
    'IBAN_CODE': _m(
        'IBAN',
        'International bank account numbers, checksum validated.',
        GROUP_GLOBAL,
    ),
    'IP_ADDRESS': _m(
        'IP address',
        'IPv4 and IPv6 addresses.',
        GROUP_GLOBAL,
        example='192.168.0.1',
    ),
    'MAC_ADDRESS': _m(
        'MAC address',
        'Hardware network addresses.',
        GROUP_GLOBAL,
        example='00:1A:2B:3C:4D:5E',
    ),
    'PHONE_NUMBER': _m(
        'Phone number',
        'International and national phone numbers.',
        GROUP_GLOBAL,
        example='+1 415-555-0142',
    ),
    'URL': _m(
        'URL',
        'Web addresses. Matches loosely and will redact ordinary links.',
        GROUP_GLOBAL,
    ),
    'PERSON': _m(
        'Person name',
        'Names of people, detected by language model rather than by pattern. '
        'Context-dependent and prone to false positives on ordinary prose.',
        GROUP_GLOBAL,
        example='Margaret Hamilton',
    ),
    'LOCATION': _m(
        'Location',
        'Places, cities and countries. Fires on ordinary prose such as '
        '"the weather in London".',
        GROUP_GLOBAL,
    ),
    'ORGANIZATION': _m(
        'Organisation',
        'Company and institution names. Context-dependent.',
        GROUP_GLOBAL,
    ),
    'NRP': _m(
        'Nationality, religion or political group',
        'Sensitive group membership mentioned in text. Context-dependent.',
        GROUP_GLOBAL,
    ),
    # -- Australia ------------------------------------------------------
    'AU_ABN': _m(
        'Australian Business Number',
        'ABN, checksum validated.',
        'Australia',
        'AU',
    ),
    'AU_ACN': _m(
        'Australian Company Number',
        'ACN, checksum validated.',
        'Australia',
        'AU',
    ),
    'AU_MEDICARE': _m(
        'Australian Medicare number',
        'Medicare card numbers, checksum validated.',
        'Australia',
        'AU',
    ),
    'AU_TFN': _m(
        'Australian Tax File Number',
        'TFN, checksum validated.',
        'Australia',
        'AU',
    ),
    # -- Canada ---------------------------------------------------------
    'CA_SIN': _m(
        'Canadian Social Insurance Number',
        'SIN, checksum validated.',
        'Canada',
        'CA',
    ),
    # -- Finland --------------------------------------------------------
    'FI_PERSONAL_IDENTITY_CODE': _m(
        'Finnish personal identity code',
        'Henkilotunnus, checksum validated.',
        'Finland',
        'FI',
    ),
    # -- Germany --------------------------------------------------------
    'DE_BSNR': _m(
        'German practice number (BSNR)',
        'Betriebsstattennummer identifying a medical practice.',
        'Germany',
        'DE',
    ),
    'DE_FUEHRERSCHEIN': _m(
        'German driving licence',
        'Fuhrerscheinnummer.',
        'Germany',
        'DE',
    ),
    'DE_HANDELSREGISTER': _m(
        'German commercial register number',
        'Handelsregisternummer.',
        'Germany',
        'DE',
    ),
    'DE_HEALTH_INSURANCE': _m(
        'German health insurance number',
        'Krankenversichertennummer.',
        'Germany',
        'DE',
    ),
    'DE_ID_CARD': _m(
        'German identity card number',
        'Personalausweisnummer.',
        'Germany',
        'DE',
    ),
    'DE_KFZ': _m(
        'German vehicle registration',
        'Kfz-Kennzeichen (number plate).',
        'Germany',
        'DE',
    ),
    'DE_LANR': _m(
        'German physician number (LANR)',
        'Lebenslange Arztnummer.',
        'Germany',
        'DE',
    ),
    'DE_PASSPORT': _m(
        'German passport number',
        'Reisepassnummer.',
        'Germany',
        'DE',
    ),
    'DE_PLZ': _m(
        'German postcode',
        'Postleitzahl. Matches any five-digit number, so expect false '
        'positives on ordinary figures.',
        'Germany',
        'DE',
    ),
    'DE_SOCIAL_SECURITY': _m(
        'German social security number',
        'Sozialversicherungsnummer.',
        'Germany',
        'DE',
    ),
    'DE_TAX_ID': _m(
        'German tax ID',
        'Steuerliche Identifikationsnummer, checksum validated.',
        'Germany',
        'DE',
    ),
    'DE_TAX_NUMBER': _m(
        'German tax number',
        'Steuernummer.',
        'Germany',
        'DE',
    ),
    'DE_VAT_ID': _m(
        'German VAT ID',
        'Umsatzsteuer-Identifikationsnummer.',
        'Germany',
        'DE',
    ),
    # -- India ----------------------------------------------------------
    'IN_AADHAAR': _m(
        'Aadhaar number',
        'UIDAI 12-digit identity number. Verhoeff checksum validated, so '
        'arbitrary 12-digit numbers are not flagged.',
        'India',
        'IN',
        example='2234 5678 9012',
    ),
    'IN_GSTIN': _m(
        'GSTIN',
        'Goods and Services Tax identification number, checksum validated.',
        'India',
        'IN',
    ),
    'IN_PAN': _m(
        'PAN',
        'Permanent Account Number. Pattern only, no checksum, so it matches '
        'loosely.',
        'India',
        'IN',
        example='ABCDE1234F',
    ),
    'IN_PASSPORT': _m(
        'Indian passport number',
        'Pattern only, no checksum.',
        'India',
        'IN',
    ),
    'IN_VEHICLE_REGISTRATION': _m(
        'Indian vehicle registration',
        'Number plate, validated against known RTO codes.',
        'India',
        'IN',
    ),
    'IN_VOTER': _m(
        'Indian voter ID',
        'EPIC number. Pattern only, no checksum.',
        'India',
        'IN',
    ),
    # -- Italy ----------------------------------------------------------
    'IT_DRIVER_LICENSE': _m(
        'Italian driving licence',
        'Patente di guida.',
        'Italy',
        'IT',
    ),
    'IT_FISCAL_CODE': _m(
        'Italian fiscal code',
        'Codice fiscale, checksum validated.',
        'Italy',
        'IT',
    ),
    'IT_IDENTITY_CARD': _m(
        'Italian identity card',
        "Carta d'identita number. Pattern only.",
        'Italy',
        'IT',
    ),
    'IT_PASSPORT': _m(
        'Italian passport number',
        'Pattern only, no checksum.',
        'Italy',
        'IT',
    ),
    'IT_VAT_CODE': _m(
        'Italian VAT code',
        'Partita IVA, checksum validated.',
        'Italy',
        'IT',
    ),
    # -- Nigeria --------------------------------------------------------
    'NG_NIN': _m(
        'Nigerian National Identification Number',
        'NIN.',
        'Nigeria',
        'NG',
    ),
    'NG_VEHICLE_REGISTRATION': _m(
        'Nigerian vehicle registration',
        'Number plate.',
        'Nigeria',
        'NG',
    ),
    # -- Philippines ----------------------------------------------------
    'PH_TIN': _m(
        'Philippine Tax Identification Number',
        'TIN.',
        'Philippines',
        'PH',
    ),
    'PH_UMID': _m(
        'Philippine UMID',
        'Unified Multi-Purpose ID number.',
        'Philippines',
        'PH',
    ),
    # -- Poland ---------------------------------------------------------
    'PL_PESEL': _m(
        'Polish PESEL',
        'National identification number, checksum validated.',
        'Poland',
        'PL',
    ),
    # -- Singapore ------------------------------------------------------
    'SG_NRIC_FIN': _m(
        'Singapore NRIC / FIN',
        'National Registration Identity Card and Foreign Identification ' 'Number.',
        'Singapore',
        'SG',
    ),
    'SG_UEN': _m(
        'Singapore UEN',
        'Unique Entity Number for registered organisations.',
        'Singapore',
        'SG',
    ),
    # -- South Africa ---------------------------------------------------
    'ZA_ID_NUMBER': _m(
        'South African ID number',
        'Checksum validated.',
        'South Africa',
        'ZA',
    ),
    # -- South Korea ----------------------------------------------------
    'KR_BRN': _m(
        'Korean Business Registration Number',
        'BRN, checksum validated.',
        'South Korea',
        'KR',
    ),
    'KR_DRIVER_LICENSE': _m(
        'Korean driving licence',
        'Driver licence number.',
        'South Korea',
        'KR',
    ),
    'KR_FRN': _m(
        'Korean Foreigner Registration Number',
        'FRN.',
        'South Korea',
        'KR',
    ),
    'KR_PASSPORT': _m(
        'Korean passport number',
        'Pattern only, no checksum.',
        'South Korea',
        'KR',
    ),
    'KR_RRN': _m(
        'Korean Resident Registration Number',
        'RRN, checksum validated.',
        'South Korea',
        'KR',
    ),
    # -- Spain ----------------------------------------------------------
    'ES_NIE': _m(
        'Spanish NIE',
        'Foreigner identity number, checksum validated.',
        'Spain',
        'ES',
    ),
    'ES_NIF': _m(
        'Spanish NIF',
        'Tax identity number, checksum validated.',
        'Spain',
        'ES',
    ),
    'ES_PASSPORT': _m(
        'Spanish passport number',
        'Pattern only, no checksum.',
        'Spain',
        'ES',
    ),
    # -- Sweden ---------------------------------------------------------
    'SE_ORGANISATIONSNUMMER': _m(
        'Swedish organisation number',
        'Organisationsnummer, checksum validated.',
        'Sweden',
        'SE',
    ),
    'SE_PERSONNUMMER': _m(
        'Swedish personal number',
        'Personnummer, checksum validated.',
        'Sweden',
        'SE',
    ),
    # -- Thailand -------------------------------------------------------
    'TH_TNIN': _m(
        'Thai national ID',
        'Thai National Identification Number, checksum validated.',
        'Thailand',
        'TH',
    ),
    # -- Turkey ---------------------------------------------------------
    'TR_LICENSE_PLATE': _m(
        'Turkish vehicle registration',
        'Number plate.',
        'Turkey',
        'TR',
    ),
    'TR_NATIONAL_ID': _m(
        'Turkish national ID',
        'T.C. Kimlik No, checksum validated.',
        'Turkey',
        'TR',
    ),
    # -- United Kingdom -------------------------------------------------
    'UK_DRIVING_LICENCE': _m(
        'UK driving licence',
        'DVLA licence number.',
        'United Kingdom',
        'GB',
    ),
    'UK_NHS': _m(
        'UK NHS number',
        'Checksum validated.',
        'United Kingdom',
        'GB',
    ),
    'UK_NINO': _m(
        'UK National Insurance number',
        'NINO. Pattern only, no checksum.',
        'United Kingdom',
        'GB',
    ),
    'UK_PASSPORT': _m(
        'UK passport number',
        'Pattern only, no checksum.',
        'United Kingdom',
        'GB',
    ),
    'UK_POSTCODE': _m(
        'UK postcode',
        'Matches loosely and will redact ordinary postcodes in addresses.',
        'United Kingdom',
        'GB',
    ),
    'UK_VEHICLE_REGISTRATION': _m(
        'UK vehicle registration',
        'Number plate.',
        'United Kingdom',
        'GB',
    ),
    # -- United States --------------------------------------------------
    'ABA_ROUTING_NUMBER': _m(
        'ABA routing number',
        'US bank routing transit number, checksum validated.',
        'United States',
        'US',
    ),
    'MEDICAL_LICENSE': _m(
        'Medical licence number',
        'DEA registration numbers, checksum validated.',
        'United States',
        'US',
    ),
    'US_BANK_NUMBER': _m(
        'US bank account number',
        'Pattern only. Matches loosely, so ordinary long numbers may be ' 'redacted.',
        'United States',
        'US',
    ),
    'US_DRIVER_LICENSE': _m(
        'US driving licence',
        'Formats vary by state, so this matches loosely.',
        'United States',
        'US',
    ),
    'US_ITIN': _m(
        'US ITIN',
        'Individual Taxpayer Identification Number.',
        'United States',
        'US',
    ),
    'US_MBI': _m(
        'US Medicare Beneficiary Identifier',
        'MBI.',
        'United States',
        'US',
    ),
    'US_NPI': _m(
        'US National Provider Identifier',
        'NPI, checksum validated.',
        'United States',
        'US',
    ),
    'US_PASSPORT': _m(
        'US passport number',
        'Pattern only, no checksum.',
        'United States',
        'US',
    ),
    'US_SSN': _m(
        'US Social Security Number',
        'SSN, with invalid ranges filtered out.',
        'United States',
        'US',
        example='123-45-6789',
    ),
}

#: Entity types with no useful upper bound on how long an occurrence can be.
#:
#: A URL has none at all, and an address-like LOCATION runs to a paragraph.
#: The rest of the catalog is identifiers: shapes with a fixed or near-fixed
#: width, the longest being EMAIL_ADDRESS at the RFC 5321 maximum of 320.
UNBOUNDED_LENGTH: frozenset = frozenset({'URL'}) | NLP_BACKED

#: Entity types a guarded stream may release text incrementally for.
#:
#: Incremental release rests on holding back a margin wider than the longest
#: entity that could straddle the release point: an occurrence starting before
#: the cut then ends inside the scanned text, so the scan either found it or
#: it is not there. That argument needs a length bound, and these are the
#: entities that have one -- see DEFAULT_MARGIN_CHARS in ``stream_guard``,
#: which is sized against this set.
#:
#: Derived from the catalog rather than listed out, which is what makes it
#: safe to leave alone. An entity type this file has never heard of -- a new
#: recogniser arriving with a Presidio upgrade -- is absent from
#: ENTITY_CATALOG, so it is absent from here, so a policy selecting it
#: buffers. Staleness costs latency, loudly, rather than quietly under-sizing
#: a margin for something already in use. That is the same reason this is not
#: an ENTITY_MAX_CHARS table: set membership is the weaker claim to maintain
#: by hand ("this entity is short" rather than "this entity is at most N"),
#: and it fails in the direction that does not matter.
INCREMENTAL_SAFE: frozenset = frozenset(ENTITY_CATALOG) - UNBOUNDED_LENGTH


def describe(entity_id: str) -> EntityMeta:
    """Presentation for one entity, with a safe fallback.

    An entity the running engine reports but this catalog has never heard of
    still has to render, otherwise upgrading Presidio would make new
    recognisers invisible in the UI while they quietly ran in production.
    """
    known = ENTITY_CATALOG.get(entity_id)
    if known is not None:
        return known

    label = entity_id.replace('_', ' ').capitalize()
    return EntityMeta(
        label=label,
        description='Detected by Presidio. No description available.',
        group=GROUP_OTHER,
    )


def group_sort_key(group: str) -> Tuple[int, str]:
    """Order groups by :data:`GROUP_ORDER`, unknown groups last."""
    try:
        return (GROUP_ORDER.index(group), '')
    except ValueError:
        return (len(GROUP_ORDER), group)
