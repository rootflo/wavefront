/**
 * Curated TTS voice / speaker catalogs for voice agent dropdowns.
 * Sourced from provider docs (Deepgram Aura, Sarvam Bulbul, Cartesia, Azure).
 */

export interface VoiceOption {
  value: string;
  label: string;
}

/** Deepgram Aura / Aura-2 model strings used as voice IDs */
export const DEEPGRAM_TTS_VOICES: VoiceOption[] = [
  { value: 'aura-2-agathe-fr', label: 'aura-2-agathe-fr' },
  { value: 'aura-2-agustina-es', label: 'aura-2-agustina-es' },
  { value: 'aura-2-alvaro-es', label: 'aura-2-alvaro-es' },
  { value: 'aura-2-ama-ja', label: 'aura-2-ama-ja' },
  { value: 'aura-2-amalthea-en', label: 'aura-2-amalthea-en' },
  { value: 'aura-2-andromeda-en', label: 'aura-2-andromeda-en' },
  { value: 'aura-2-antonia-es', label: 'aura-2-antonia-es' },
  { value: 'aura-2-apollo-en', label: 'aura-2-apollo-en' },
  { value: 'aura-2-aquila-es', label: 'aura-2-aquila-es' },
  { value: 'aura-2-arcas-en', label: 'aura-2-arcas-en' },
  { value: 'aura-2-aries-en', label: 'aura-2-aries-en' },
  { value: 'aura-2-asteria-en', label: 'aura-2-asteria-en' },
  { value: 'aura-2-athena-en', label: 'aura-2-athena-en' },
  { value: 'aura-2-atlas-en', label: 'aura-2-atlas-en' },
  { value: 'aura-2-aurelia-de', label: 'aura-2-aurelia-de' },
  { value: 'aura-2-aurora-en', label: 'aura-2-aurora-en' },
  { value: 'aura-2-beatrix-nl', label: 'aura-2-beatrix-nl' },
  { value: 'aura-2-callista-en', label: 'aura-2-callista-en' },
  { value: 'aura-2-carina-es', label: 'aura-2-carina-es' },
  { value: 'aura-2-celeste-es', label: 'aura-2-celeste-es' },
  { value: 'aura-2-cesare-it', label: 'aura-2-cesare-it' },
  { value: 'aura-2-cinzia-it', label: 'aura-2-cinzia-it' },
  { value: 'aura-2-cora-en', label: 'aura-2-cora-en' },
  { value: 'aura-2-cordelia-en', label: 'aura-2-cordelia-en' },
  { value: 'aura-2-cornelia-nl', label: 'aura-2-cornelia-nl' },
  { value: 'aura-2-daphne-nl', label: 'aura-2-daphne-nl' },
  { value: 'aura-2-delia-en', label: 'aura-2-delia-en' },
  { value: 'aura-2-demetra-it', label: 'aura-2-demetra-it' },
  { value: 'aura-2-diana-es', label: 'aura-2-diana-es' },
  { value: 'aura-2-dionisio-it', label: 'aura-2-dionisio-it' },
  { value: 'aura-2-draco-en', label: 'aura-2-draco-en' },
  { value: 'aura-2-ebisu-ja', label: 'aura-2-ebisu-ja' },
  { value: 'aura-2-elara-de', label: 'aura-2-elara-de' },
  { value: 'aura-2-electra-en', label: 'aura-2-electra-en' },
  { value: 'aura-2-elio-it', label: 'aura-2-elio-it' },
  { value: 'aura-2-estrella-es', label: 'aura-2-estrella-es' },
  { value: 'aura-2-fabian-de', label: 'aura-2-fabian-de' },
  { value: 'aura-2-flavio-it', label: 'aura-2-flavio-it' },
  { value: 'aura-2-fujin-ja', label: 'aura-2-fujin-ja' },
  { value: 'aura-2-gloria-es', label: 'aura-2-gloria-es' },
  { value: 'aura-2-harmonia-en', label: 'aura-2-harmonia-en' },
  { value: 'aura-2-hector-fr', label: 'aura-2-hector-fr' },
  { value: 'aura-2-helena-en', label: 'aura-2-helena-en' },
  { value: 'aura-2-hera-en', label: 'aura-2-hera-en' },
  { value: 'aura-2-hermes-en', label: 'aura-2-hermes-en' },
  { value: 'aura-2-hestia-nl', label: 'aura-2-hestia-nl' },
  { value: 'aura-2-hyperion-en', label: 'aura-2-hyperion-en' },
  { value: 'aura-2-iris-en', label: 'aura-2-iris-en' },
  { value: 'aura-2-izanami-ja', label: 'aura-2-izanami-ja' },
  { value: 'aura-2-janus-en', label: 'aura-2-janus-en' },
  { value: 'aura-2-javier-es', label: 'aura-2-javier-es' },
  { value: 'aura-2-julius-de', label: 'aura-2-julius-de' },
  { value: 'aura-2-juno-en', label: 'aura-2-juno-en' },
  { value: 'aura-2-jupiter-en', label: 'aura-2-jupiter-en' },
  { value: 'aura-2-kara-de', label: 'aura-2-kara-de' },
  { value: 'aura-2-lara-de', label: 'aura-2-lara-de' },
  { value: 'aura-2-lars-nl', label: 'aura-2-lars-nl' },
  { value: 'aura-2-leda-nl', label: 'aura-2-leda-nl' },
  { value: 'aura-2-livia-it', label: 'aura-2-livia-it' },
  { value: 'aura-2-luciano-es', label: 'aura-2-luciano-es' },
  { value: 'aura-2-luna-en', label: 'aura-2-luna-en' },
  { value: 'aura-2-maia-it', label: 'aura-2-maia-it' },
  { value: 'aura-2-mars-en', label: 'aura-2-mars-en' },
  { value: 'aura-2-melia-it', label: 'aura-2-melia-it' },
  { value: 'aura-2-minerva-en', label: 'aura-2-minerva-en' },
  { value: 'aura-2-neptune-en', label: 'aura-2-neptune-en' },
  { value: 'aura-2-nestor-es', label: 'aura-2-nestor-es' },
  { value: 'aura-2-odysseus-en', label: 'aura-2-odysseus-en' },
  { value: 'aura-2-olivia-es', label: 'aura-2-olivia-es' },
  { value: 'aura-2-ophelia-en', label: 'aura-2-ophelia-en' },
  { value: 'aura-2-orion-en', label: 'aura-2-orion-en' },
  { value: 'aura-2-orpheus-en', label: 'aura-2-orpheus-en' },
  { value: 'aura-2-pandora-en', label: 'aura-2-pandora-en' },
  { value: 'aura-2-phoebe-en', label: 'aura-2-phoebe-en' },
  { value: 'aura-2-pluto-en', label: 'aura-2-pluto-en' },
  { value: 'aura-2-rhea-nl', label: 'aura-2-rhea-nl' },
  { value: 'aura-2-roman-nl', label: 'aura-2-roman-nl' },
  { value: 'aura-2-sander-nl', label: 'aura-2-sander-nl' },
  { value: 'aura-2-saturn-en', label: 'aura-2-saturn-en' },
  { value: 'aura-2-selena-es', label: 'aura-2-selena-es' },
  { value: 'aura-2-selene-en', label: 'aura-2-selene-en' },
  { value: 'aura-2-silvia-es', label: 'aura-2-silvia-es' },
  { value: 'aura-2-sirio-es', label: 'aura-2-sirio-es' },
  { value: 'aura-2-thalia-en', label: 'aura-2-thalia-en' },
  { value: 'aura-2-theia-en', label: 'aura-2-theia-en' },
  { value: 'aura-2-uzume-ja', label: 'aura-2-uzume-ja' },
  { value: 'aura-2-valerio-es', label: 'aura-2-valerio-es' },
  { value: 'aura-2-vesta-en', label: 'aura-2-vesta-en' },
  { value: 'aura-2-viktoria-de', label: 'aura-2-viktoria-de' },
  { value: 'aura-2-zeus-en', label: 'aura-2-zeus-en' },
  { value: 'aura-angus-en', label: 'aura-angus-en' },
  { value: 'aura-arcas-en', label: 'aura-arcas-en' },
  { value: 'aura-asteria-en', label: 'aura-asteria-en' },
  { value: 'aura-athena-en', label: 'aura-athena-en' },
  { value: 'aura-helios-en', label: 'aura-helios-en' },
  { value: 'aura-hera-en', label: 'aura-hera-en' },
  { value: 'aura-luna-en', label: 'aura-luna-en' },
  { value: 'aura-orion-en', label: 'aura-orion-en' },
  { value: 'aura-orpheus-en', label: 'aura-orpheus-en' },
  { value: 'aura-perseus-en', label: 'aura-perseus-en' },
  { value: 'aura-stella-en', label: 'aura-stella-en' },
  { value: 'aura-zeus-en', label: 'aura-zeus-en' },
];

/** Sarvam Bulbul v3 short speaker names */
export const SARVAM_V3_SPEAKERS: VoiceOption[] = [
  { value: 'shubh', label: 'shubh' },
  { value: 'aditya', label: 'aditya' },
  { value: 'ritu', label: 'ritu' },
  { value: 'priya', label: 'priya' },
  { value: 'neha', label: 'neha' },
  { value: 'rahul', label: 'rahul' },
  { value: 'pooja', label: 'pooja' },
  { value: 'rohan', label: 'rohan' },
  { value: 'simran', label: 'simran' },
  { value: 'kavya', label: 'kavya' },
  { value: 'amit', label: 'amit' },
  { value: 'dev', label: 'dev' },
  { value: 'ishita', label: 'ishita' },
  { value: 'shreya', label: 'shreya' },
  { value: 'ratan', label: 'ratan' },
  { value: 'varun', label: 'varun' },
  { value: 'manan', label: 'manan' },
  { value: 'sumit', label: 'sumit' },
  { value: 'roopa', label: 'roopa' },
  { value: 'kabir', label: 'kabir' },
  { value: 'aayan', label: 'aayan' },
  { value: 'ashutosh', label: 'ashutosh' },
  { value: 'advait', label: 'advait' },
  { value: 'anand', label: 'anand' },
  { value: 'tanya', label: 'tanya' },
  { value: 'tarun', label: 'tarun' },
  { value: 'sunny', label: 'sunny' },
  { value: 'mani', label: 'mani' },
  { value: 'gokul', label: 'gokul' },
  { value: 'vijay', label: 'vijay' },
  { value: 'shruti', label: 'shruti' },
  { value: 'suhani', label: 'suhani' },
  { value: 'mohit', label: 'mohit' },
  { value: 'kavitha', label: 'kavitha' },
  { value: 'rehan', label: 'rehan' },
  { value: 'soham', label: 'soham' },
  { value: 'rupali', label: 'rupali' },
];

/** Sarvam Bulbul v4 Flash persona speaker IDs (222) */
export const SARVAM_V4_SPEAKERS: VoiceOption[] = [
  { value: 'aarti_hi_customer', label: 'aarti · hi · customer' },
  { value: 'aayan_hi_conversational', label: 'aayan · hi · conversational' },
  { value: 'aditi_en_stories', label: 'aditi · en · stories' },
  { value: 'aditya_hi_conversational', label: 'aditya · hi · conversational' },
  { value: 'aditya_hi_sales', label: 'aditya · hi · sales' },
  { value: 'advait_hi_character', label: 'advait · hi · character' },
  { value: 'amelia_en_conversational', label: 'amelia · en · conversational' },
  { value: 'amit_hi_conversational', label: 'amit · hi · conversational' },
  { value: 'anand_hi_documentary', label: 'anand · hi · documentary' },
  { value: 'anand_hi_news', label: 'anand · hi · news' },
  { value: 'anand_pa_conversation', label: 'anand · pa · conversation' },
  { value: 'anand_pa_customer', label: 'anand · pa · customer' },
  { value: 'aparna_en_companion', label: 'aparna · en · companion' },
  { value: 'aparna_en_edtech', label: 'aparna · en · edtech' },
  { value: 'aparna_hi_customer', label: 'aparna · hi · customer' },
  { value: 'aparna_hi_kyc', label: 'aparna · hi · kyc' },
  { value: 'aravind_ta_ads', label: 'aravind · ta · ads' },
  { value: 'aravind_ta_suspense', label: 'aravind · ta · suspense' },
  { value: 'arnab_bn_conversation', label: 'arnab · bn · conversation' },
  { value: 'aryaman_hi_ads', label: 'aryaman · hi · ads' },
  { value: 'ashok_hi_character', label: 'ashok · hi · character' },
  { value: 'ashok_hi_news', label: 'ashok · hi · news' },
  { value: 'ashutosh_hi_conversational', label: 'ashutosh · hi · conversational' },
  { value: 'ashwin_en_sports', label: 'ashwin · en · sports' },
  { value: 'ashwin_en_sports_energetic', label: 'ashwin · en · sports_energetic' },
  { value: 'bhavik_gu_conversation', label: 'bhavik · gu · conversation' },
  { value: 'bimal_bn_suspense', label: 'bimal · bn · suspense' },
  { value: 'chaitra_hi_customer', label: 'chaitra · hi · customer' },
  { value: 'chaitra_kn_conversation', label: 'chaitra · kn · conversation' },
  { value: 'chaitra_kn_narration', label: 'chaitra · kn · narration' },
  { value: 'chandrika_en_stories', label: 'chandrika · en · stories' },
  { value: 'chetan_kn_conversation', label: 'chetan · kn · conversation' },
  { value: 'chhavi_hi_kids', label: 'chhavi · hi · kids' },
  { value: 'chirag_hi_social', label: 'chirag · hi · social' },
  { value: 'dev_en_conversational', label: 'dev · en · conversational' },
  { value: 'dev_en_recovery', label: 'dev · en · recovery' },
  { value: 'deven_en_conversation', label: 'deven · en · conversation' },
  { value: 'girish_en_devotional', label: 'girish · en · devotional' },
  { value: 'girish_en_documentary', label: 'girish · en · documentary' },
  { value: 'girish_hi_devotional', label: 'girish · hi · devotional' },
  { value: 'gokul_ta_narration', label: 'gokul · ta · narration' },
  { value: 'harpreet_pa_narration', label: 'harpreet · pa · narration' },
  { value: 'ishita_en_customer', label: 'ishita · en · customer' },
  { value: 'ishita_en_medical', label: 'ishita · en · medical' },
  { value: 'ishita_en_numbers', label: 'ishita · en · numbers' },
  { value: 'ishita_en_social', label: 'ishita · en · social' },
  { value: 'ishita_en_stories', label: 'ishita · en · stories' },
  { value: 'ishita_enhi_companion', label: 'ishita · enhi · companion' },
  { value: 'ishita_enhi_customer', label: 'ishita · enhi · customer' },
  { value: 'ishita_enhi_customer_expressive', label: 'ishita · enhi · customer_expressive' },
  { value: 'ishita_hi_ads', label: 'ishita · hi · ads' },
  { value: 'ishita_hi_ads_informal', label: 'ishita · hi · ads_informal' },
  { value: 'ishita_hi_banking', label: 'ishita · hi · banking' },
  { value: 'ishita_hi_devotional', label: 'ishita · hi · devotional' },
  { value: 'ishita_hi_edtech', label: 'ishita · hi · edtech' },
  { value: 'ishita_hi_numbers', label: 'ishita · hi · numbers' },
  { value: 'ishita_hi_social', label: 'ishita · hi · social' },
  { value: 'ishita_mr_conversational', label: 'ishita · mr · conversational' },
  { value: 'jaspal_pa_banking', label: 'jaspal · pa · banking' },
  { value: 'kabir_hi_conversational', label: 'kabir · hi · conversational' },
  { value: 'kalpit_en_edtech', label: 'kalpit · en · edtech' },
  { value: 'kavitha_te_conversation', label: 'kavitha · te · conversation' },
  { value: 'kavitha_te_narration', label: 'kavitha · te · narration' },
  { value: 'kavya_hi_conversational', label: 'kavya · hi · conversational' },
  { value: 'kunal_hi_kids', label: 'kunal · hi · kids' },
  { value: 'mahesh_hi_documentary', label: 'mahesh · hi · documentary' },
  { value: 'manan_hi_conversational', label: 'manan · hi · conversational' },
  { value: 'mani_hi_conversational', label: 'mani · hi · conversational' },
  { value: 'mani_hi_devotional', label: 'mani · hi · devotional' },
  { value: 'mohit_hi_conversational', label: 'mohit · hi · conversational' },
  { value: 'mrunal_mr_narration', label: 'mrunal · mr · narration' },
  { value: 'mukul_hi_ads', label: 'mukul · hi · ads' },
  { value: 'mukul_hi_suspense', label: 'mukul · hi · suspense' },
  { value: 'mukul_mr_stories', label: 'mukul · mr · stories' },
  { value: 'nachiket_en_ads', label: 'nachiket · en · ads' },
  { value: 'nachiket_hi_devotional', label: 'nachiket · hi · devotional' },
  { value: 'neha_en_customer', label: 'neha · en · customer' },
  { value: 'neha_en_latenight', label: 'neha · en · latenight' },
  { value: 'neha_mr_narration', label: 'neha · mr · narration' },
  { value: 'nilesh_mr_conversation', label: 'nilesh · mr · conversation' },
  { value: 'nupur_en_kids', label: 'nupur · en · kids' },
  { value: 'ojas_en_social', label: 'ojas · en · social' },
  { value: 'payal_en_edtech', label: 'payal · en · edtech' },
  { value: 'pooja_gu_conversational', label: 'pooja · gu · conversational' },
  { value: 'pooja_gu_customer', label: 'pooja · gu · customer' },
  { value: 'pooja_te_conversation', label: 'pooja · te · conversation' },
  { value: 'priya_hi_recovery', label: 'priya · hi · recovery' },
  { value: 'rahul_hi_conversational', label: 'rahul · hi · conversational' },
  { value: 'ratan_hi_customer_expressive', label: 'ratan · hi · customer_expressive' },
  { value: 'ratan_hi_devotional', label: 'ratan · hi · devotional' },
  { value: 'ratan_hi_documentary', label: 'ratan · hi · documentary' },
  { value: 'ratan_hi_latenight', label: 'ratan · hi · latenight' },
  { value: 'ratan_hi_latenight_warm', label: 'ratan · hi · latenight_warm' },
  { value: 'ratan_hi_recovery', label: 'ratan · hi · recovery' },
  { value: 'ratan_hi_social', label: 'ratan · hi · social' },
  { value: 'ratan_hi_sports', label: 'ratan · hi · sports' },
  { value: 'rehan_hi_social', label: 'rehan · hi · social' },
  { value: 'ritu_en_edtech', label: 'ritu · en · edtech' },
  { value: 'ritu_en_latenight', label: 'ritu · en · latenight' },
  { value: 'ritu_en_medical', label: 'ritu · en · medical' },
  { value: 'ritu_en_reels', label: 'ritu · en · reels' },
  { value: 'ritu_hi_ads_formal', label: 'ritu · hi · ads_formal' },
  { value: 'ritu_hi_ads_informal', label: 'ritu · hi · ads_informal' },
  { value: 'ritu_hi_banking', label: 'ritu · hi · banking' },
  { value: 'ritu_hi_conversation', label: 'ritu · hi · conversation' },
  { value: 'ritu_hi_customer', label: 'ritu · hi · customer' },
  { value: 'ritu_hi_customer_utility', label: 'ritu · hi · customer_utility' },
  { value: 'ritu_hi_customer_warm', label: 'ritu · hi · customer_warm' },
  { value: 'ritu_hi_edtech', label: 'ritu · hi · edtech' },
  { value: 'ritu_hi_edtech_bot', label: 'ritu · hi · edtech_bot' },
  { value: 'ritu_hi_insurance', label: 'ritu · hi · insurance' },
  { value: 'ritu_hi_kids', label: 'ritu · hi · kids' },
  { value: 'ritu_hi_medical', label: 'ritu · hi · medical' },
  { value: 'ritu_hi_reels', label: 'ritu · hi · reels' },
  { value: 'ritu_hi_sales', label: 'ritu · hi · sales' },
  { value: 'ritu_hi_social', label: 'ritu · hi · social' },
  { value: 'ritu_hi_social_lively', label: 'ritu · hi · social_lively' },
  { value: 'ritu_mr_insurance', label: 'ritu · mr · insurance' },
  { value: 'ritu_mr_narration', label: 'ritu · mr · narration' },
  { value: 'rohan_en_recovery', label: 'rohan · en · recovery' },
  { value: 'roopa_bn_conversational', label: 'roopa · bn · conversational' },
  { value: 'roopa_en_conversational', label: 'roopa · en · conversational' },
  { value: 'roopa_hi_companion', label: 'roopa · hi · companion' },
  { value: 'roopa_hi_conversational', label: 'roopa · hi · conversational' },
  { value: 'roopa_hi_market', label: 'roopa · hi · market' },
  { value: 'roopa_hi_narration', label: 'roopa · hi · narration' },
  { value: 'roopa_hi_recovery', label: 'roopa · hi · recovery' },
  { value: 'rupali_mr_stories', label: 'rupali · mr · stories' },
  { value: 'rustom_en_suspense', label: 'rustom · en · suspense' },
  { value: 'sanchita_en_companion', label: 'sanchita · en · companion' },
  { value: 'sanchita_en_insurance', label: 'sanchita · en · insurance' },
  { value: 'sanchita_en_market', label: 'sanchita · en · market' },
  { value: 'sanchita_en_recovery', label: 'sanchita · en · recovery' },
  { value: 'sanchita_en_social', label: 'sanchita · en · social' },
  { value: 'sanchita_enhi_companion', label: 'sanchita · enhi · companion' },
  { value: 'sanchita_hi_ads_formal', label: 'sanchita · hi · ads_formal' },
  { value: 'sanchita_hi_ads_informal', label: 'sanchita · hi · ads_informal' },
  { value: 'sanchita_hi_assistant', label: 'sanchita · hi · assistant' },
  { value: 'sanchita_hi_banking', label: 'sanchita · hi · banking' },
  { value: 'sanchita_hi_edtech', label: 'sanchita · hi · edtech' },
  { value: 'sanchita_hi_feedback', label: 'sanchita · hi · feedback' },
  { value: 'sanchita_hi_interview', label: 'sanchita · hi · interview' },
  { value: 'sanchita_hi_kyc', label: 'sanchita · hi · kyc' },
  { value: 'sanchita_hi_market', label: 'sanchita · hi · market' },
  { value: 'sanchita_hi_romantic', label: 'sanchita · hi · romantic' },
  { value: 'sanchita_hi_social', label: 'sanchita · hi · social' },
  { value: 'sarang_en_narration', label: 'sarang · en · narration' },
  { value: 'sarika_hi_conversation', label: 'sarika · hi · conversation' },
  { value: 'shabana_en_edtech', label: 'shabana · en · edtech' },
  { value: 'shalini_en_companion', label: 'shalini · en · companion' },
  { value: 'shalini_en_customer', label: 'shalini · en · customer' },
  { value: 'shalini_enhi_companion', label: 'shalini · enhi · companion' },
  { value: 'shalini_enhi_customer', label: 'shalini · enhi · customer' },
  { value: 'shalini_hi_companion', label: 'shalini · hi · companion' },
  { value: 'shalini_hi_social', label: 'shalini · hi · social' },
  { value: 'shilpa_hi_narration', label: 'shilpa · hi · narration' },
  { value: 'shreya_hi_conversational', label: 'shreya · hi · conversational' },
  { value: 'shreya_hi_news', label: 'shreya · hi · news' },
  { value: 'shruti_hi_edtech', label: 'shruti · hi · edtech' },
  { value: 'shubh_en_ads', label: 'shubh · en · ads' },
  { value: 'shubh_en_audiobook', label: 'shubh · en · audiobook' },
  { value: 'shubh_en_narration', label: 'shubh · en · narration' },
  { value: 'shubh_en_narration_gentle', label: 'shubh · en · narration_gentle' },
  { value: 'shubh_en_numbers', label: 'shubh · en · numbers' },
  { value: 'shubh_en_recovery', label: 'shubh · en · recovery' },
  { value: 'shubh_en_sports', label: 'shubh · en · sports' },
  { value: 'shubh_enhi_ads', label: 'shubh · enhi · ads' },
  { value: 'shubh_enhi_banking', label: 'shubh · enhi · banking' },
  { value: 'shubh_enhi_companion', label: 'shubh · enhi · companion' },
  { value: 'shubh_hi_ads', label: 'shubh · hi · ads' },
  { value: 'shubh_hi_customer', label: 'shubh · hi · customer' },
  { value: 'shubh_hi_devotional', label: 'shubh · hi · devotional' },
  { value: 'shubh_hi_ecomm', label: 'shubh · hi · ecomm' },
  { value: 'shubh_hi_recovery', label: 'shubh · hi · recovery' },
  { value: 'shubh_hi_stories_dramatic', label: 'shubh · hi · stories_dramatic' },
  { value: 'shubh_hi_stories_mixed', label: 'shubh · hi · stories_mixed' },
  { value: 'simran_en_ads', label: 'simran · en · ads' },
  { value: 'simran_en_automobile', label: 'simran · en · automobile' },
  { value: 'simran_en_conversation', label: 'simran · en · conversation' },
  { value: 'simran_en_customer', label: 'simran · en · customer' },
  { value: 'simran_en_edtech', label: 'simran · en · edtech' },
  { value: 'simran_en_edtech_bot', label: 'simran · en · edtech_bot' },
  { value: 'simran_en_narration', label: 'simran · en · narration' },
  { value: 'simran_en_recovery', label: 'simran · en · recovery' },
  { value: 'simran_en_sales', label: 'simran · en · sales' },
  { value: 'simran_en_therapist', label: 'simran · en · therapist' },
  { value: 'simran_enhi_banking_expressive', label: 'simran · enhi · banking_expressive' },
  { value: 'simran_enhi_companion', label: 'simran · enhi · companion' },
  { value: 'simran_enhi_customer', label: 'simran · enhi · customer' },
  { value: 'simran_hi_assistant', label: 'simran · hi · assistant' },
  { value: 'simran_hi_automobile', label: 'simran · hi · automobile' },
  { value: 'simran_hi_conversation', label: 'simran · hi · conversation' },
  { value: 'simran_hi_latenight', label: 'simran · hi · latenight' },
  { value: 'simran_hi_narration', label: 'simran · hi · narration' },
  { value: 'simran_hi_news', label: 'simran · hi · news' },
  { value: 'simran_hi_news_breaking', label: 'simran · hi · news_breaking' },
  { value: 'simran_hi_recovery', label: 'simran · hi · recovery' },
  { value: 'simran_hi_sales', label: 'simran · hi · sales' },
  { value: 'simran_hi_social_energetic', label: 'simran · hi · social_energetic' },
  { value: 'simran_hi_social_excited', label: 'simran · hi · social_excited' },
  { value: 'soham_mr_narration', label: 'soham · mr · narration' },
  { value: 'sophia_en_conversational', label: 'sophia · en · conversational' },
  { value: 'suchitra_hi_ecomm', label: 'suchitra · hi · ecomm' },
  { value: 'suchitra_kn_narration', label: 'suchitra · kn · narration' },
  { value: 'suhani_hi_social', label: 'suhani · hi · social' },
  { value: 'suman_hi_companion', label: 'suman · hi · companion' },
  { value: 'sumit_hi_conversational', label: 'sumit · hi · conversational' },
  { value: 'sunny_en_social', label: 'sunny · en · social' },
  { value: 'sunny_enhi_customer', label: 'sunny · enhi · customer' },
  { value: 'sunny_hi_ads', label: 'sunny · hi · ads' },
  { value: 'sunny_hi_reels', label: 'sunny · hi · reels' },
  { value: 'tanya_hi_narration', label: 'tanya · hi · narration' },
  { value: 'tarun_hi_conversational', label: 'tarun · hi · conversational' },
  { value: 'tarun_hi_sales', label: 'tarun · hi · sales' },
  { value: 'tarun_te_narration', label: 'tarun · te · narration' },
  { value: 'vaibhav_hi_social', label: 'vaibhav · hi · social' },
  { value: 'vandana_hi_ecomm', label: 'vandana · hi · ecomm' },
  { value: 'varun_en_ads', label: 'varun · en · ads' },
  { value: 'varun_en_suspense', label: 'varun · en · suspense' },
  { value: 'vijay_ta_narration', label: 'vijay · ta · narration' },
  { value: 'vipul_hi_social', label: 'vipul · hi · social' },
  { value: 'zarina_en_conversation', label: 'zarina · en · conversation' },
];

/** Featured Cartesia public voices */
export const CARTESIA_FEATURED_VOICES: VoiceOption[] = [
  { value: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4', label: 'Skylar (en-US Female)' },
  { value: '47c38ca4-5f35-497b-b1a3-415245fb35e1', label: 'Daniel (en-US Male)' },
  { value: '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc', label: 'Jacqueline (en-US Female)' },
  { value: '62ae83ad-4f6a-430b-af41-a9bede9286ca', label: 'Gemma (en-GB Female)' },
  { value: 'ef191366-f52f-447a-a398-ed8c0f2943a1', label: 'Archie (en-GB Male)' },
];

/** Common Azure Neural voices */
export const AZURE_NEURAL_VOICES: VoiceOption[] = [
  { value: 'en-US-JennyNeural', label: 'en-US-JennyNeural' },
  { value: 'en-US-GuyNeural', label: 'en-US-GuyNeural' },
  { value: 'en-US-AriaNeural', label: 'en-US-AriaNeural' },
  { value: 'en-US-DavisNeural', label: 'en-US-DavisNeural' },
  { value: 'en-US-AmberNeural', label: 'en-US-AmberNeural' },
  { value: 'en-US-AnaNeural', label: 'en-US-AnaNeural' },
  { value: 'en-US-AshleyNeural', label: 'en-US-AshleyNeural' },
  { value: 'en-US-BrandonNeural', label: 'en-US-BrandonNeural' },
  { value: 'en-US-ChristopherNeural', label: 'en-US-ChristopherNeural' },
  { value: 'en-US-CoraNeural', label: 'en-US-CoraNeural' },
  { value: 'en-US-ElizabethNeural', label: 'en-US-ElizabethNeural' },
  { value: 'en-US-EricNeural', label: 'en-US-EricNeural' },
  { value: 'en-US-JacobNeural', label: 'en-US-JacobNeural' },
  { value: 'en-US-MichelleNeural', label: 'en-US-MichelleNeural' },
  { value: 'en-US-MonicaNeural', label: 'en-US-MonicaNeural' },
  { value: 'en-US-SaraNeural', label: 'en-US-SaraNeural' },
  { value: 'en-IN-NeerjaNeural', label: 'en-IN-NeerjaNeural' },
  { value: 'en-IN-PrabhatNeural', label: 'en-IN-PrabhatNeural' },
  { value: 'en-GB-SoniaNeural', label: 'en-GB-SoniaNeural' },
  { value: 'en-GB-RyanNeural', label: 'en-GB-RyanNeural' },
  { value: 'hi-IN-SwaraNeural', label: 'hi-IN-SwaraNeural' },
  { value: 'hi-IN-MadhurNeural', label: 'hi-IN-MadhurNeural' },
  { value: 'es-ES-ElviraNeural', label: 'es-ES-ElviraNeural' },
  { value: 'es-MX-DaliaNeural', label: 'es-MX-DaliaNeural' },
  { value: 'fr-FR-DeniseNeural', label: 'fr-FR-DeniseNeural' },
  { value: 'de-DE-KatjaNeural', label: 'de-DE-KatjaNeural' },
  { value: 'ja-JP-NanamiNeural', label: 'ja-JP-NanamiNeural' },
  { value: 'zh-CN-XiaoxiaoNeural', label: 'zh-CN-XiaoxiaoNeural' },
];

const SARVAM_V4_LANG_TAGS: Record<string, string[]> = {
  en: ['en', 'enhi'],
  hi: ['hi', 'enhi'],
  bn: ['bn'],
  gu: ['gu'],
  kn: ['kn'],
  mr: ['mr'],
  pa: ['pa'],
  ta: ['ta'],
  te: ['te'],
};

function titleCase(value: string): string {
  return value
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

/** Human-readable label for a voice ID (keeps `value` as the stored ID). */
export function formatVoiceOption(provider: string, option: VoiceOption): VoiceOption {
  if (provider === 'deepgram') {
    const match = option.value.match(/^aura(?:-2)?-(.+)-([a-z]{2})$/i);
    if (match) {
      return { value: option.value, label: `${titleCase(match[1])} (${match[2]})` };
    }
  }

  if (provider === 'sarvam') {
    if (option.value.includes('_')) {
      const [name, lang, ...styleParts] = option.value.split('_');
      const style = styleParts.join(' ');
      const label = style ? `${titleCase(name)} · ${lang} · ${style}` : `${titleCase(name)}${lang ? ` · ${lang}` : ''}`;
      return { value: option.value, label };
    }
    return { value: option.value, label: titleCase(option.value) };
  }

  if (provider === 'azure') {
    // en-US-JennyNeural -> Jenny (en-US)
    const match = option.value.match(/^([a-z]{2}-[A-Z]{2})-(.+)Neural$/);
    if (match) {
      return { value: option.value, label: `${match[2]} (${match[1]})` };
    }
  }

  // Cartesia and others already store a friendly label
  if (option.label && option.label !== option.value) {
    return option;
  }

  return option;
}

function withFriendlyLabels(provider: string, options: VoiceOption[]): VoiceOption[] {
  return options.map((option) => formatVoiceOption(provider, option));
}

function filterSarvamV4ByLanguage(langCode: string): VoiceOption[] {
  const tags = SARVAM_V4_LANG_TAGS[langCode];
  if (!tags) return SARVAM_V4_SPEAKERS;
  return SARVAM_V4_SPEAKERS.filter((voice) => {
    const parts = voice.value.split('_');
    const tag = parts[1];
    return tags.includes(tag);
  });
}

function filterDeepgramByLanguage(langCode: string): VoiceOption[] {
  const suffix = `-${langCode}`;
  const matched = DEEPGRAM_TTS_VOICES.filter((v) => v.value.endsWith(suffix));
  // Fall back to English Aura-2 voices when language has no catalog entry
  if (matched.length === 0 && langCode !== 'en') {
    return DEEPGRAM_TTS_VOICES.filter((v) => v.value.endsWith('-en') && v.value.startsWith('aura-2-'));
  }
  return matched.length > 0 ? matched : DEEPGRAM_TTS_VOICES;
}

function getAllVoicesForProvider(provider: string, model: string | undefined): VoiceOption[] {
  if (provider === 'deepgram') return DEEPGRAM_TTS_VOICES;
  if (provider === 'sarvam') {
    return model === 'bulbul:v4-flash' ? SARVAM_V4_SPEAKERS : SARVAM_V3_SPEAKERS;
  }
  if (provider === 'cartesia') return CARTESIA_FEATURED_VOICES;
  if (provider === 'azure') return AZURE_NEURAL_VOICES;
  return [];
}

/**
 * Resolve selectable TTS voice options for a provider/model/language.
 * Pass languageCode undefined/empty for the full provider catalog (default voice).
 * Returns empty array when the provider uses account-specific IDs (ElevenLabs).
 */
export function getTtsVoiceOptions(
  provider: string | undefined,
  model: string | undefined,
  languageCode?: string
): VoiceOption[] {
  if (!provider) return [];

  let options: VoiceOption[] = [];

  if (!languageCode) {
    options = getAllVoicesForProvider(provider, model);
  } else if (provider === 'deepgram') {
    options = filterDeepgramByLanguage(languageCode);
  } else if (provider === 'sarvam') {
    options = model === 'bulbul:v4-flash' ? filterSarvamV4ByLanguage(languageCode) : SARVAM_V3_SPEAKERS;
  } else if (provider === 'cartesia') {
    options = CARTESIA_FEATURED_VOICES;
  } else if (provider === 'azure') {
    const byLang = AZURE_NEURAL_VOICES.filter((v) =>
      v.value.toLowerCase().startsWith(`${languageCode.toLowerCase()}-`)
    );
    options = byLang.length > 0 ? byLang : AZURE_NEURAL_VOICES;
  }

  return withFriendlyLabels(provider, options);
}

/** Look up a friendly display name for a stored voice ID. */
export function getTtsVoiceLabel(provider: string | undefined, model: string | undefined, voiceId: string): string {
  if (!provider || !voiceId) return voiceId;
  const match = getAllVoicesForProvider(provider, model).find((option) => option.value === voiceId);
  if (match) return formatVoiceOption(provider, match).label;
  return formatVoiceOption(provider, { value: voiceId, label: voiceId }).label;
}

/** Whether voiceId is selectable for this provider/model(/language). Free-text providers always valid. */
export function isTtsVoiceIdValid(
  provider: string | undefined,
  model: string | undefined,
  voiceId: string,
  languageCode?: string
): boolean {
  if (!voiceId) return false;
  const options = getTtsVoiceOptions(provider, model, languageCode);
  if (options.length === 0) return true;
  return options.some((option) => option.value === voiceId);
}

/**
 * Pick a default voice ID for a provider/model(/language).
 * Returns undefined when the provider has no catalog (e.g. ElevenLabs).
 */
export function getDefaultTtsVoiceId(
  provider: string | undefined,
  model: string | undefined,
  languageCode?: string
): string | undefined {
  const options = getTtsVoiceOptions(provider, model, languageCode);
  if (options.length === 0) return undefined;

  const preferredByProvider: Record<string, string[]> = {
    deepgram: ['aura-2-asteria-en', 'aura-2-thalia-en', 'aura-asteria-en'],
    sarvam: ['shubh', 'priya', 'anushka'],
    azure: ['en-US-JennyNeural', 'en-US-AriaNeural'],
  };

  for (const id of preferredByProvider[provider || ''] || []) {
    if (options.some((option) => option.value === id)) return id;
  }

  if (!languageCode) {
    if (provider === 'deepgram') {
      const en = options.find((option) => option.value.endsWith('-en'));
      if (en) return en.value;
    }
    if (provider === 'azure') {
      const en = options.find((option) => option.value.toLowerCase().startsWith('en-'));
      if (en) return en.value;
    }
  }

  return options[0].value;
}
