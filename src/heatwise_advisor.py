"""HeatWise AI — Role-Specific Heatwave Advisory Engine.

Converts verified heatwave alerts, weather forecasts, and official NDMA/IMD
guidelines into personalized, actionable safety recommendations and checklists
for specific user groups. Supports English, Hindi, and Marathi.
Uses Groq AI (LLaMA 3.3) with an authoritative grounded fallback engine.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported Roles & Metadata
# ---------------------------------------------------------------------------

ROLES_METADATA = {
    "outdoor_workers": {
        "id": "outdoor_workers",
        "title": {
            "en": "Outdoor & Construction Workers",
            "hi": "निर्माण व खुले मैदान के श्रमिक",
            "mr": "बांधकाम व मैदानी कामगार",
        },
        "description": {
            "en": "Construction crews, agricultural laborers, street vendors, delivery executives, and utility workers.",
            "hi": "निर्माण श्रमिक, कृषि मजदूर, फेरीवाले, डिलीवरी कर्मचारी और रखरखाव दल।",
            "mr": "बांधकाम मजूर, शेतमजूर, फेरीवाले, डिलिव्हरी कामगार आणि देखभाल कर्मचारी.",
        },
        "icon": "hard-hat",
        "category": "Occupational Safety",
    },
    "school_admins": {
        "id": "school_admins",
        "title": {
            "en": "School Administrators & Educators",
            "hi": "विद्यालय प्रशासक व शिक्षक",
            "mr": "शाळा प्रशासन व शिक्षक",
        },
        "description": {
            "en": "Principals, sports coaches, hostel wardens, and school transport coordinators.",
            "hi": "प्राचार्य, खेल प्रशिक्षक, छात्रावास वार्डन और स्कूल परिवहन समन्वयक।",
            "mr": "मुख्याध्यापक, क्रीडा शिक्षक, वसतिगृह अधीक्षक आणि शालेय वाहतूक समन्वयक.",
        },
        "icon": "school",
        "category": "Child & Youth Welfare",
    },
    "older_adults": {
        "id": "older_adults",
        "title": {
            "en": "Older Adults & Vulnerable Individuals",
            "hi": "वरिष्ठ नागरिक व संवेदनशील व्यक्ति",
            "mr": "ज्येष्ठ नागरिक व संवेदनशील व्यक्ती",
        },
        "description": {
            "en": "Seniors (60+), individuals with cardiovascular or renal conditions, pregnant women, and caregivers.",
            "hi": "वरिष्ठ नागरिक, हृदय या गुर्दे के रोगी, गर्भवती महिलाएं और उनकी देखभाल करने वाले।",
            "mr": "ज्येष्ठ नागरिक, हृदय किंवा मूत्रपिंडाचे आजार असलेले रुग्ण, गरोदर महिला व काळजीवाहक.",
        },
        "icon": "heart-pulse",
        "category": "Public Health & Vulnerability",
    },
    "event_organisers": {
        "id": "event_organisers",
        "title": {
            "en": "Event Organizers & Crowd Managers",
            "hi": "कार्यक्रम आयोजक व भीड़ प्रबंधक",
            "mr": "कार्यक्रम आयोजक व गर्दी व्यवस्थापक",
        },
        "description": {
            "en": "Organizers of sporting tournaments, cultural/religious festivals, political rallies, and outdoor banquets.",
            "hi": "खेल प्रतियोगिताएं, धार्मिक उत्सव, जनसभाएं और विवाह समारोह आयोजित करने वाले।",
            "mr": "क्रीडा स्पर्धा, धार्मिक उत्सव, सभा आणि सार्वजनिक समारंभ आयोजक.",
        },
        "icon": "calendar-check",
        "category": "Event Operations",
    },
    "municipal_officials": {
        "id": "municipal_officials",
        "title": {
            "en": "Municipal Officials & City Planners",
            "hi": "नगर निगम अधिकारी व आपदा प्रबंधन",
            "mr": "महानगरपालिका अधिकारी व आपत्ती व्यवस्थापन",
        },
        "description": {
            "en": "Municipal commissioners, district disaster officers, ward officers, and public health departments.",
            "hi": "नगर आयुक्त, जिला आपदा प्रबंधन अधिकारी, वार्ड अधिकारी और जन स्वास्थ्य विभाग।",
            "mr": "पालिका आयुक्त, जिल्हा आपत्ती व्यवस्थापन अधिकारी, प्रभाग अधिकारी आणि सार्वजनिक आरोग्य विभाग.",
        },
        "icon": "building-shield",
        "category": "Governance & Civil Protection",
    },
}

SUPPORTED_LANGUAGES = {
    "en": {"code": "en", "label": "English", "native": "English"},
    "hi": {"code": "hi", "label": "Hindi", "native": "हिन्दी"},
    "mr": {"code": "mr", "label": "Marathi", "native": "मराठी"},
}

# ---------------------------------------------------------------------------
# NDMA / IMD Grounded Reference Knowledge Base (Fallback & Baseline Rules)
# ---------------------------------------------------------------------------

NDMA_GROUNDED_RULES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "outdoor_workers": {
        "GREEN": {
            "en": {
                "summary": "Normal seasonal conditions. Routine hydration and standard sun protection are recommended.",
                "priority_alert": "Normal Work Schedule Permitted — Maintain Standard Hydration",
                "precautions": [
                    "Carry at least 2 liters of drinking water per shift.",
                    "Take standard 10-minute rest breaks during peak noon hours (12:00 - 15:00).",
                    "Wear lightweight, breathable, light-colored cotton clothing.",
                    "Use head covers or brimmed hats when working directly under the sun.",
                ],
                "checklist": [
                    {"task": "Verify potable drinking water availability at site", "timeframe": "08:00", "priority": "Medium"},
                    {"task": "Inspect shaded rest shelter areas", "timeframe": "10:00", "priority": "Low"},
                    {"task": "Confirm first-aid box is stocked with ORS packets", "timeframe": "Daily", "priority": "Medium"},
                ],
                "emergency_protocol": "If any worker experiences dizziness or excessive thirst, move to shade immediately and provide salted lemon water or ORS.",
            },
            "hi": {
                "summary": "मौसम सामान्य है। नियमित रूप से जलपान करें और धूप से सामान्य बचाव रखें।",
                "priority_alert": "सामान्य कार्य समय — नियमित जलपान बनाए रखें",
                "precautions": [
                    "प्रत्येक कार्य पाली में कम से कम 2 लीटर पीने का पानी साथ रखें।",
                    "दोपहर 12:00 से 15:00 के बीच 10 मिनट का सामान्य विश्राम लें।",
                    "हल्के रंग के, ढीले सूती कपड़े पहनें।",
                    "धूप में काम करते समय टोपी या सूती गमछा सिर पर बांधें।",
                ],
                "checklist": [
                    {"task": "कार्यस्थल पर स्वच्छ पेयजल की उपलब्धता जांचें", "timeframe": "प्रातः 08:00", "priority": "Medium"},
                    {"task": "छायादार विश्राम स्थल का निरीक्षण करें", "timeframe": "प्रातः 10:00", "priority": "Low"},
                    {"task": "प्राथमिक चिकित्सा पेटी में ओआरएस (ORS) पैकेट सुनिश्चित करें", "timeframe": "दैनिक", "priority": "Medium"},
                ],
                "emergency_protocol": "यदि किसी श्रमिक को चक्कर आए या कमजोरी लगे, तो तुरंत छाया में लिटाएं और ओआरएस का घोल पिलाएं।",
            },
            "mr": {
                "summary": "हवामान सामान्य आहे. नियमित पाणी प्या आणि उन्हापासून नेहमीची काळजी घ्या.",
                "priority_alert": "नेहमीचे कामाचे तास — पाण्याचे प्रमाण पुरेसे ठेवा",
                "precautions": [
                    "प्रत्येक पाळीत किमान २ लिटर पिण्याचे पाणी सोबत ठेवा.",
                    "दुपारी १२:०० ते १५:०० दरम्यान १० मिनिटांची नेहमीची विश्रांती घ्या.",
                    "हलके आणि सैल सुती कपडे वापरा.",
                    "उन्हात काम करताना डोक्यावर टोपी किंवा सुती रुमाल बांधा.",
                ],
                "checklist": [
                    {"task": "कामाच्या ठिकाणी स्वच्छ पिण्याच्या पाण्याची तपासणी करा", "timeframe": "सकाळी ०८:००", "priority": "Medium"},
                    {"task": "सावलीच्या विश्राम स्थळाची पाहणी करा", "timeframe": "सकाळी १०:००", "priority": "Low"},
                    {"task": "प्रथमोपचार पेटीत ओआरएस (ORS) पाकिटे असल्याची खात्री करा", "timeframe": "दैनिक", "priority": "Medium"},
                ],
                "emergency_protocol": "कोणत्याही कामगारास चक्कर किंवा जास्त तहान जाणवल्यास त्वरित सावलीत बसवून ओआरएसचे पाणी द्यावे.",
            },
        },
        "YELLOW": {
            "en": {
                "summary": "Elevated temperatures detected. Heat watch active. Increase hydration frequency and monitor workers for early heat exhaustion.",
                "priority_alert": "Heat Watch: Implement Scheduled Rest Breaks in Shade",
                "precautions": [
                    "Drink 250ml of water or electrolyte solution every 30 minutes, even if not feeling thirsty.",
                    "Mandate 15-minute shaded rest breaks every 60 minutes between 11:30 and 15:30.",
                    "Avoid heavy direct-sun lifting tasks during the peak solar radiation window (12:00 - 15:00).",
                    "Ensure wet towels and cool water are accessible for immediate cooling.",
                ],
                "checklist": [
                    {"task": "Set up designated shaded rest zone with adequate cross-ventilation", "timeframe": "09:00", "priority": "High"},
                    {"task": "Distribute ORS/lemon-salt water to all outdoor teams", "timeframe": "11:00 & 14:00", "priority": "High"},
                    {"task": "Assign a safety buddy to monitor co-workers for slurred speech or fatigue", "timeframe": "Continuous", "priority": "Medium"},
                    {"task": "Stock portable ice packs in the site medical kit", "timeframe": "Before noon", "priority": "Medium"},
                ],
                "emergency_protocol": "Heat exhaustion signs: heavy sweating, weakness, cold pale skin, fast pulse. Move to shade, loosen clothes, apply wet cloth, sip ORS.",
            },
            "hi": {
                "summary": "तापमान में वृद्धि दर्ज की गई है। सतर्कता बरतें, श्रमिकों के जलपान की दर बढ़ाएं और थकान पर नजर रखें।",
                "priority_alert": "हीट वॉच: छाया में निर्धारित विश्राम समय लागू करें",
                "precautions": [
                    "प्यास न लगने पर भी हर 30 मिनट में 250 मिलीलीटर पानी या नींबू-नमक का घोल पिएं।",
                    "सुबह 11:30 से दोपहर 15:30 के बीच प्रति घंटे 15 मिनट का छायादार विश्राम अनिवार्य करें।",
                    "दोपहर 12:00 से 15:00 के सबसे गर्म समय में भारी वजन उठाने वाले कार्य सीमित करें।",
                    "शरीर को ठंडा रखने के लिए गीले तौलिए और ठंडा पानी पास रखें।",
                ],
                "checklist": [
                    {"task": "हवादार छायादार विश्राम स्थल स्थापित करें", "timeframe": "प्रातः 09:00", "priority": "High"},
                    {"task": "सभी श्रमिकों को ओआरएस या छाछ/नींबू पानी वितरित करें", "timeframe": "11:00 और 14:00", "priority": "High"},
                    {"task": "श्रमिकों में सुस्ती या चक्कर की निगरानी के लिए 'बडी सिस्टम' लागू करें", "timeframe": "निरंतर", "priority": "Medium"},
                    {"task": "साइट प्राथमिक चिकित्सा किट में बर्फ/कोल्ड पैक रखें", "timeframe": "दोपहर से पहले", "priority": "Medium"},
                ],
                "emergency_protocol": "अधिक पसीना, कमजोरी या तेज धड़कन दिखने पर तुरंत पंखे या छाया में लिटाएं, कपड़े ढीले करें और ओआरएस पिलाएं।",
            },
            "mr": {
                "summary": "तापमानात वाढ झाली आहे. पाण्याचे प्रमाण वाढवा आणि कामगारांमध्ये उष्माघाताची लक्षणे आढळल्यास त्वरित लक्ष द्या.",
                "priority_alert": "हीट वॉच: सावलीमध्ये विश्रांतीची वेळ ठरवून द्या",
                "precautions": [
                    "तहान नसली तरी दर ३० मिनिटांनी २५० मिली पाणी किंवा लिंबू सरबत प्या.",
                    "सकाळी ११:३० ते दुपारी ०३:३० दरम्यान दर तासाला १५ मिनिटे सावलीत विश्रांती अनिवार्य करा.",
                    "दुपारी १२:०० ते १५:०० दरम्यान अतिश्रम आणि वजन उचलण्याची कामे टाळा.",
                    "शरीराचे तापमान नियंत्रणात ठेवण्यासाठी ओले कापड जवळ ठेवा.",
                ],
                "checklist": [
                    {"task": "हवेशीर सावलीचे विश्राम केंद्र सज्ज करा", "timeframe": "सकाळी ०९:००", "priority": "High"},
                    {"task": "कामगारांना ओआरएस किंवा ताक/लिंबू सरबत वाटप करा", "timeframe": "११:०० व १४:००", "priority": "High"},
                    {"task": "सहकाऱ्यांमधील थकवा तपासण्यासाठी जोडीदार (बडी) पद्धत वापरा", "timeframe": "सतत", "priority": "Medium"},
                    {"task": "साइटवरील प्रथमोपचार पेटीत बर्फ व ओआरएस सज्ज ठेवा", "timeframe": "दुपारी १२ पूर्वी", "priority": "Medium"},
                ],
                "emergency_protocol": "खूप घाम, अशक्तपणा किंवा चक्कर आल्यास ताबडतोब सावलीत नेऊन पाय थोडे उंच ठेवा, कपडे सैल करा आणि पाणी द्या.",
            },
        },
        "ORANGE": {
            "en": {
                "summary": "Severe heat risk alert. Outdoor work between 12:00 and 16:00 poses severe risk of heat stroke. Immediate shift rescheduling required.",
                "priority_alert": "High Heatwave Alert: Reschedule Shifts & Mandate 20-Min Rest per Hour",
                "precautions": [
                    "Reschedule shifts to split-hours: 06:00 - 11:00 and 16:30 - 19:30 to avoid peak solar radiation.",
                    "Suspend non-essential strenuous roof, scaffolding, and asphalt paving operations between 12:00 and 16:00.",
                    "Provide cold water, electral/ORS, and fresh buttermilk at every workstation.",
                    "Mandate 20-minute rest every 40 minutes of outdoor exertion.",
                    "Designate a trained site heat-safety marshal with digital forehead thermometers.",
                ],
                "checklist": [
                    {"task": "Execute split-shift schedule (shift morning start to 06:00 AM)", "timeframe": "06:00", "priority": "High"},
                    {"task": "Verify chilled water barrels (minimum 5 liters per worker per shift)", "timeframe": "07:30", "priority": "High"},
                    {"task": "Install misting fans or evaporative coolers in worker rest shelters", "timeframe": "10:00", "priority": "High"},
                    {"task": "Hourly wellness check and temperature spot-check for vulnerable workers", "timeframe": "Hourly 11:00-16:00", "priority": "High"},
                    {"task": "Pre-arrange emergency vehicle on standby for rapid hospital transport", "timeframe": "08:00 - 18:00", "priority": "High"},
                ],
                "emergency_protocol": "CRITICAL: Heat Stroke Warning! Symptoms: Body temp > 103°F (39.5°C), hot dry skin (no sweat), confusion, unconsciousness. Call 108 immediately. Douse body with cold water, place ice packs in armpits and groin. Do NOT give fluids if unconscious.",
            },
            "hi": {
                "summary": "गंभीर लू (हीटवेव) की चेतावनी। दोपहर 12:00 से 16:00 के बीच खुले में काम करने से हीट स्ट्रोक का गंभीर खतरा है। कार्य पाली बदलना अनिवार्य है।",
                "priority_alert": "हाई हीटवेव अलर्ट: कार्य पाली बदलें — प्रति घंटे 20 मिनट का विश्राम दें",
                "precautions": [
                    "कार्य पाली को दो भागों में बांटें: सुबह 06:00 से 11:00 और शाम 16:30 से 19:30।",
                    "दोपहर 12:00 से 16:00 के बीच छत, मचान और डामर सड़क निर्माण के भारी कार्य तुरंत रोकें।",
                    "प्रत्येक कार्यस्थल पर ठंडा पानी, ओआरएस और छाछ की निरंतर आपूर्ति रखें।",
                    "धूप में काम करने के हर 40 मिनट पर 20 मिनट का विश्राम अनिवार्य करें।",
                    "तापमान मापने के लिए थर्मल स्कैनर और प्राथमिक उपचारक तैनात करें।",
                ],
                "checklist": [
                    {"task": "कार्य समय सुबह 06:00 बजे से शुरू करने का आदेश लागू करें", "timeframe": "प्रातः 06:00", "priority": "High"},
                    {"task": "प्रति श्रमिक न्यूनतम 5 लीटर ठंडे पेयजल की व्यवस्था सुनिश्चित करें", "timeframe": "प्रातः 07:30", "priority": "High"},
                    {"task": "विश्राम टेंट में मिस्टिंग पंखे या कूलर चालू करें", "timeframe": "प्रातः 10:00", "priority": "High"},
                    {"task": "11:00 से 16:00 के बीच प्रत्येक घंटे श्रमिकों की स्वास्थ्य जांच करें", "timeframe": "प्रति घंटे", "priority": "High"},
                    {"task": "आपातकालीन वाहन (एम्बुलेंस/वाहन) अस्पताल ले जाने हेतु स्टैंडबाय रखें", "timeframe": "पूरे दिन", "priority": "High"},
                ],
                "emergency_protocol": "अत्यंत गंभीर: हीट स्ट्रोक के लक्षण—तेज बुखार (>103°F), त्वचा का लाल व सूखा होना, बेहोशी या भ्रम। तुरंत 108 डायल करें। सिर और गर्दन पर बर्फ रखें, ठंडा पानी छिड़कें। बेहोश व्यक्ति को पानी न पिलाएं।",
            },
            "mr": {
                "summary": "तीव्र उष्णतेची लाट (हीटवेव्ह). दुपारी १२:०० ते १६:०० दरम्यान उन्हात काम करणे जीवितास धोकादायक ठरू शकते. कामाच्या वेळा बदलणे बंधनकारक आहे.",
                "priority_alert": "तीव्र उष्णता इशारा: कामाच्या वेळा बदला — दर तासाला २० मिनिटे विश्रांती अनिवार्य",
                "precautions": [
                    "कामाची पाळी दोन भागात विभागून घ्या: सकाळी ०६:०० ते ११:०० आणि संध्याकाळी १६:३० ते १९:३०.",
                    "दुपारी १२:०० ते १६:०० दरम्यान उन्हातील अवजड कामे, डांबरीकरण व स्लॅबचे काम पूर्णपणे थांबवा.",
                    "प्रत्येक केंद्रावर थंड पाणी, ओआरएस आणि ताकाची सतत उपलब्धता ठेवा.",
                    "उन्हातील ४० मिनिटांच्या कामानंतर २० मिनिटे थंड सावलीत विश्रांती अनिवार्य करा.",
                    "कामगारांचे तापमान तपासण्यासाठी थर्मामीटर व सुरक्षा प्रमुख नियुक्त करा.",
                ],
                "checklist": [
                    {"task": "सकाळी ०६:०० वाजता काम सुरू करण्याचे परिपत्रक लागू करा", "timeframe": "सकाळी ०६:००", "priority": "High"},
                    {"task": "प्रत्येक कामगारासाठी किमान ५ लिटर पिण्याचे पाणी उपलब्ध असल्याची खात्री करा", "timeframe": "सकाळी ०७:३०", "priority": "High"},
                    {"task": "विश्राम शेडमध्ये कुलर किंवा पाणी फवारणी पंखे सुरू करा", "timeframe": "सकाळी १०:००", "priority": "High"},
                    {"task": "११:०० ते १६:०० दरम्यान प्रत्येक तासाला कामगारांची प्रकृती तपासा", "timeframe": "दर तासाला", "priority": "High"},
                    {"task": "तात्काळ रुग्णालयात नेण्यासाठी वाहन/रुग्णवाहिका सज्ज ठेवा", "timeframe": "संपूर्ण पाळीत", "priority": "High"},
                ],
                "emergency_protocol": "अतितातडीचा इशारा: उष्माघाताची लक्षणे—शरीराचे तापमान १०३°F पेक्षा जास्त, घाम थांबणे, त्वचा कोरडी पडणे, ग्लानी येणे. त्वरित १०८ वर संपर्क साधा. डोक्यावर व काखेत बर्फाच्या पट्ट्या ठेवा. बेशुद्ध असल्यास पाणी पाजू नका.",
            },
        },
        "RED": {
            "en": {
                "summary": "EXTREME HEAT EMERGENCY. Fatal heat exposure danger. Complete prohibition of direct-sun manual labor between 11:30 and 16:30 mandated under NDMA guidelines.",
                "priority_alert": "Red Heat Emergency: Halt Direct Outdoor Work 11:30 - 16:30",
                "precautions": [
                    "Total stoppage of outdoor construction, digging, and roofing operations during peak danger hours (11:30 - 16:30).",
                    "Move any urgent work exclusively to early morning (05:30 - 10:30) or night shifts with adequate lighting.",
                    "Mandatory cooling centers with air coolers, rehydration salts, and first-aid medical personnel on-site.",
                    "No worker is permitted to work alone — buddy observation protocol strictly in force.",
                    "Provide paid thermal recess per state disaster mitigation directives.",
                ],
                "checklist": [
                    {"task": "Issue formal work stoppage notice for 11:30 - 16:30 window", "timeframe": "06:00", "priority": "High"},
                    {"task": "Operate cooled break shelters with continuous ice water & glucose supply", "timeframe": "All Day", "priority": "High"},
                    {"task": "Conduct mandatory vitals check (pulse & temperature) for all crew members", "timeframe": "11:00 & 16:30", "priority": "High"},
                    {"task": "Verify dedicated air-conditioned evacuation vehicle stationed at site", "timeframe": "07:00", "priority": "High"},
                    {"task": "Coordinate with nearest municipal hospital casualty ward for heat-stroke protocols", "timeframe": "09:00", "priority": "High"},
                ],
                "emergency_protocol": "LIFE THREATENING EMERGENCY: Heat stroke is a medical catastrophe. Call 108 instantly. Strip outer clothing. Immerse or douse victim in cold water. Fan aggressively. Place ice packs on neck, armpits, and groin. Transport to emergency ICU immediately.",
            },
            "hi": {
                "summary": "चरम लू आपातकाल (रेड अलर्ट)। जानलेवा गर्मी का खतरा। एनडीएमए (NDMA) दिशा-निर्देशों के तहत 11:30 से 16:30 तक खुले में शारीरिक श्रम पर पूर्ण प्रतिबंध।",
                "priority_alert": "रेड हीट इमरजेंसी: 11:30 से 16:30 तक खुले में समस्त कार्य तुरंत बंद करें",
                "precautions": [
                    "सुबह 11:30 से शाम 16:30 तक खुले में निर्माण, खुदाई और भारी शारीरिक श्रम पूरी तरह बंद रखें।",
                    "अनिवार्य कार्य केवल तड़के (05:30 - 10:30) अथवा पर्याप्त रोशनी में रात्रि पाली में करें।",
                    "कार्यस्थल पर एयर कूलर युक्त आपातकालीन कूलिंग शेड और प्रशिक्षित स्वास्थ्यकर्मी तैनात करें।",
                    "किसी भी श्रमिक को अकेला काम न करने दें — बडी सिस्टम सख्ती से लागू करें।",
                    "आपदा प्रबंधन नियमों के तहत श्रमिकों के वेतन में कटौती किए बिना थर्मल विराम दें।",
                ],
                "checklist": [
                    {"task": "11:30 से 16:30 के लिए कार्य स्थगन का औपचारिक नोटिस जारी करें", "timeframe": "प्रातः 06:00", "priority": "High"},
                    {"task": "एयर-कूलर युक्त शेड में ठंडा पानी, ग्लूकोज व ओआरएस की निरंतर आपूर्ति रखें", "timeframe": "पूरे दिन", "priority": "High"},
                    {"task": "सभी श्रमिकों की पल्स और शरीर के तापमान की अनिवार्य जांच करें", "timeframe": "11:00 व 16:30", "priority": "High"},
                    {"task": "आपातकालीन एयर-कंडीशंड वाहन को साइट पर तैनात रखें", "timeframe": "प्रातः 07:00", "priority": "High"},
                    {"task": "निकटतम सरकारी अस्पताल के इमरजेंसी वार्ड से पूर्व संपर्क स्थापित करें", "timeframe": "प्रातः 09:00", "priority": "High"},
                ],
                "emergency_protocol": "जानलेवा आपातकाल: हीट स्ट्रोक होने पर तुरंत 108 पर कॉल करें। कपड़े हटाकर पूरे शरीर पर ठंडा पानी डालें। पंखा चलाएं। गर्दन, कांख और जांघों पर बर्फ रखें। तुरंत आईसीयू (ICU) अस्पताल पहुंचाएं।",
            },
            "mr": {
                "summary": "अति-गंभीर उष्णता आणीबाणी (रेड अलर्ट). जिवाला थेट धोका. एनडीएमए (NDMA) नियमांनुसार सकाळी ११:३० ते दुपारी १६:३० दरम्यान उघड्यावरील अंगमेहनतीची कामे पूर्णपणे बंद ठेवा.",
                "priority_alert": "रेड हीट आणीबाणी: ११:३० ते १६:३० दरम्यान उन्हातील सर्व कामे तात्काळ बंद करा",
                "precautions": [
                    "सकाळी ११:३० ते दुपारी १६:३० या जीवघेण्या वेळेत बांधकाम, रस्ते दुरुस्ती व खोदकाम पूर्णपणे थांबवा.",
                    "केवळ पहाटे ०५:३० ते १०:३० किंवा रात्रीच्या वेळी प्रकाश व्यवस्थेत काम करा.",
                    "कूलर आणि प्रथमोपचार सुविधा असलेले वातानुकूलित तात्पुरते केंद्र साइटवर सज्ज ठेवा.",
                    "कोणत्याही कामगाराला एकटे काम करू देऊ नका — सहकाऱ्यांवर लक्ष ठेवणे बंधनकारक.",
                    "आपत्ती व्यवस्थापन नियमांनुसार वेतनात कपात न करता उष्णता सुट्टी जाहीर करा.",
                ],
                "checklist": [
                    {"task": "११:३० ते १६:३० कामाची सुट्टी देणारे औपचारिक परिपत्रक जारी करा", "timeframe": "सकाळी ०६:००", "priority": "High"},
                    {"task": "थंड शेडमध्ये बर्फ, पाणी, ग्लुकोज आणि ओआरएसची अखंड व्यवस्था ठेवा", "timeframe": "दिवसभर", "priority": "High"},
                    {"task": "सर्व कामगारांचे शरीराचे तापमान व नाडीचे ठोके तपासा", "timeframe": "११:०० व १६:३०", "priority": "High"},
                    {"task": "तातडीने नेण्यासाठी वातानुकूलित वाहन साइटवर तयार ठेवा", "timeframe": "सकाळी ०७:००", "priority": "High"},
                    {"task": "जवळच्या महापालिका रुग्णालयातील आपत्कालीन विभागाशी संपर्क ठेवा", "timeframe": "सकाळी ०९:००", "priority": "High"},
                ],
                "emergency_protocol": "जीवावर बेतलेली आणीबाणी: उष्माघात झाल्यास तात्काळ १०८ वर फोन करा. कपडे सैल करून अंगावर गार पाणी ओता. मान, काख आणि जांघेत बर्फाच्या पिशव्या लावा. तातडीने रुग्णालयात दाखल करा.",
            },
        },
    },
    "school_admins": {
        "GREEN": {
            "en": {
                "summary": "Normal seasonal conditions for schools. Regular academic and physical education schedules permitted.",
                "priority_alert": "Normal School Schedule Permitted — Promote Regular Student Hydration",
                "precautions": [
                    "Remind students during morning roll call to finish their personal water bottles.",
                    "Keep water dispensers and filtration units cleaned and fully operational.",
                    "Allow breathable cotton uniforms and comfortable footwear.",
                    "Standard physical education exercises allowed with routine water intervals.",
                ],
                "checklist": [
                    {"task": "Inspect clean drinking water coolers across student wings", "timeframe": "08:00", "priority": "Medium"},
                    {"task": "Check ventilation and ceiling fans in classrooms", "timeframe": "08:30", "priority": "Low"},
                    {"task": "Confirm school infirmary has basic ORS and first-aid supplies", "timeframe": "Weekly", "priority": "Medium"},
                ],
                "emergency_protocol": "For mild student fatigue, allow rest in shaded staff room and provide lemon water.",
            },
            "hi": {
                "summary": "विद्यालयों हेतु सामान्य मौसमी परिस्थितियां। नियमित खेलकूद और शैक्षणिक कक्षाएं सुचारु रूप से चलेंगी।",
                "priority_alert": "सामान्य विद्यालय संचालन — नियमित जलपान को प्रोत्साहित करें",
                "precautions": [
                    "प्रार्थना सभा में छात्रों को नियमित पानी पीने की आदत डालने के लिए प्रेरित करें।",
                    "स्कूल के वाटर कूलर और फिल्टर नियमित रूप से साफ रखें।",
                    "आरामदायक व हल्के सूती गणवेश (यूनिफॉर्म) की अनुमति दें।",
                    "खेलकूद कक्षाओं के दौरान बीच-बीच में पानी पीने का समय दें।",
                ],
                "checklist": [
                    {"task": "सभी विंगों में स्वच्छ पेयजल की उपलब्धता जांचें", "timeframe": "प्रातः 08:00", "priority": "Medium"},
                    {"task": "कक्षाओं में पंखों और हवा के प्रवाह की जांच करें", "timeframe": "प्रातः 08:30", "priority": "Low"},
                    {"task": "प्राथमिक चिकित्सा कक्ष में ओआरएस पैकेट सुनिश्चित करें", "timeframe": "साप्ताहिक", "priority": "Medium"},
                ],
                "emergency_protocol": "यदि किसी छात्र को थकावट लगे, तो उसे छायादार कमरे में बैठाकर पानी या नींबू पानी दें।",
            },
            "mr": {
                "summary": "शाळांसाठी हवामान सामान्य आहे. नियमित शैक्षणिक व क्रीडा तास नेहमीप्रमाणे सुरू ठेवावेत.",
                "priority_alert": "नियमित शाळा वेळापत्रक — विद्यार्थ्यांना पाणी पिण्यास प्रोत्साहित करा",
                "precautions": [
                    "सकाळच्या प्रार्थनेवेळी विद्यार्थ्यांना पाण्याची बाटली संपवण्याची आठवण करून द्या.",
                    "शाळेतील पिण्याच्या पाण्याचे कुलर आणि फिल्टर स्वच्छ ठेवा.",
                    "सैल व सुती गणवेश वापरण्यास मुभा द्या.",
                    "क्रीडा तासांदरम्यान पाणी पिण्यासाठी छोटे ब्रेक द्या.",
                ],
                "checklist": [
                    {"task": "पिण्याच्या पाण्याच्या सर्व नळांची व कुलरची तपासणी करा", "timeframe": "सकाळी ०८:००", "priority": "Medium"},
                    {"task": "वर्गातील पंखे चालू असल्याची खात्री करा", "timeframe": "सकाळी ०८:३०", "priority": "Low"},
                    {"task": "आजारी कक्षात ओआरएस पावडर उपलब्ध असल्याची खात्री करा", "timeframe": "साप्ताहिक", "priority": "Medium"},
                ],
                "emergency_protocol": "विद्यार्थ्याला थकवा जाणवल्यास सावलीत बसवून लिंबू सरबत किंवा पाणी द्यावे.",
            },
        },
        "YELLOW": {
            "en": {
                "summary": "Heat watch active. Higher daytime temperatures anticipated. Precautionary water bells and sports timing adjustments advised.",
                "priority_alert": "Heat Watch: Shift Vigorous Outdoor Sports to Early Morning",
                "precautions": [
                    "Move vigorous outdoor sports drills to before 09:30 AM; avoid direct midday field drills.",
                    "Sound a school-wide 'Water Bell' at 10:00 AM and 01:00 PM to mandate hydration breaks.",
                    "Ensure shaded play areas during lunch recess; discourage running under open sun.",
                    "Verify bus windows or vents are open before students board in afternoon.",
                ],
                "checklist": [
                    {"task": "Reschedule sports activities to indoor gymnasium or early morning", "timeframe": "08:00", "priority": "High"},
                    {"task": "Sound dedicated 'Water Bell' for student hydration", "timeframe": "10:00 & 13:00", "priority": "High"},
                    {"task": "Inspect campus shaded shelters during lunch break", "timeframe": "12:00", "priority": "Medium"},
                    {"task": "Stock infirmary with chilled water and oral electrolyte packets", "timeframe": "09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "Heat exhaustion: move student to cool room, loosen tie/collar, apply cold wet towel to forehead, offer sips of ORS.",
            },
            "hi": {
                "summary": "हीट वॉच सक्रिय। दोपहर के समय अधिक तापमान की संभावना। खेलकूद के समय में बदलाव व वाटर बेल लागू करें।",
                "priority_alert": "हीट वॉच: भारी खेलकूद सुबह 09:30 से पहले पूरे करें",
                "precautions": [
                    "मैदानी खेल और व्यायाम सुबह 09:30 बजे से पहले कराएं; दोपहर में धूप में न दौड़ाएं।",
                    "सुबह 10:00 और दोपहर 01:00 बजे 'वाटर बेल' बजाकर सभी छात्रों को पानी पिलाएं।",
                    "भोजन अवकाश (लंच) में बच्चों को छायादार स्थानों पर ही खेलने दें।",
                    "छुट्टी के समय स्कूल बसों के खिड़की-पंखे चालू रखें ताकि बसें अधिक गर्म न हों।",
                ],
                "checklist": [
                    {"task": "खेलकूद की समय-सारणी में बदलाव का नोटिस दें", "timeframe": "प्रातः 08:00", "priority": "High"},
                    {"task": "दिन में दो बार वाटर बेल बजाएं", "timeframe": "10:00 और 13:00", "priority": "High"},
                    {"task": "छायादार खेल प्रांगण का निरीक्षण करें", "timeframe": "दोपहर 12:00", "priority": "Medium"},
                    {"task": "डिस्पेंसरी में ठंडा पानी और ओआरएस उपलब्ध रखें", "timeframe": "प्रातः 09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "छात्र को चक्कर या सिरदर्द होने पर तुरंत ठंडे कमरे में लाएं, टाई-बेल्ट ढीले करें और ओआरएस का घोल पिलाएं।",
            },
            "mr": {
                "summary": "हीट वॉच सक्रिय. दुपारच्या तापमानात वाढ अपेक्षित. मैदानी खेळांच्या वेळा बदला आणि वॉटर बेल वाजवा.",
                "priority_alert": "हीट वॉच: मैदानी खेळ सकाळी ०९:३० पूर्वी पूर्ण करा",
                "precautions": [
                    "मैदानातील खेळ आणि कवायती सकाळी ०९:३० च्या आधी घ्या; दुपारच्या उन्हात मैदानावर जाऊ देऊ नका.",
                    "सकाळी १०:०० आणि दुपारी ०१:०० वाजता पाणी पिण्यासाठी विशेष वॉटर बेल वाजवा.",
                    "दुपारच्या सुट्टीत विद्यार्थ्यांना सावलीतच राहण्याच्या सूचना द्या.",
                    "शाळा सुटताना बसेसमधील हवा खेळती असल्याची खात्री करा.",
                ],
                "checklist": [
                    {"task": "क्रीडा तासांच्या वेळा सकाळी लवकर हलवण्याचे आदेश द्या", "timeframe": "सकाळी ०८:००", "priority": "High"},
                    {"task": "विद्यार्थ्यांसाठी पाणी पिण्याची घंटा (वॉटर बेल) वाजवा", "timeframe": "१०:०० व १३:००", "priority": "High"},
                    {"task": "सुट्टीच्या वेळी सावलीच्या जागेची पाहणी करा", "timeframe": "दुपारी १२:००", "priority": "Medium"},
                    {"task": "प्रथमोपचार कक्षात थंड पाणी व ओआरएस सज्ज ठेवा", "timeframe": "सकाळी ०९:००", "priority": "Medium"},
                ],
                "emergency_protocol": "विद्यार्थ्याला मळमळ किंवा ग्लानी आल्यास सावलीत बसवा, कपाळावर थंड पाण्याचा रुमाल ठेवा आणि ओआरएस द्या.",
            },
        },
        "ORANGE": {
            "en": {
                "summary": "Severe heat advisory for schools. High vulnerability for children due to lower heat dissipation efficiency. Suspend outdoor activities.",
                "priority_alert": "Cancel Outdoor Sports & Assemblies — Shift to Morning School Hours",
                "precautions": [
                    "Suspend all outdoor physical education, playground sessions, and open-ground morning assemblies after 08:30 AM.",
                    "Implement 'Water Bells' every 45 minutes to remind students and teachers to drink water.",
                    "Ensure ceiling fans and cross-ventilation are functional; convert hot top-floor classrooms to shaded lower halls.",
                    "School buses must be well-ventilated; never leave children unattended inside parked vehicles.",
                    "Keep oral rehydration salts (ORS) and glucose ready in the infirmary.",
                ],
                "checklist": [
                    {"task": "Issue circular restricting all sports/drills to indoor halls", "timeframe": "07:30", "priority": "High"},
                    {"task": "Sound school-wide 'Water Bell' every 45 minutes", "timeframe": "Every 45m", "priority": "High"},
                    {"task": "Inspect water coolers and filters across all academic blocks", "timeframe": "08:00", "priority": "High"},
                    {"task": "Equip infirmary with ice packs, ORS, and electronic thermometers", "timeframe": "08:00", "priority": "High"},
                    {"task": "Send SMS advisory to parents regarding light cotton uniforms & water bottles", "timeframe": "Previous evening", "priority": "Medium"},
                ],
                "emergency_protocol": "Child heat exhaustion: headache, nausea, fainting, heavy sweating. Move child to air-conditioned staffroom, loosen uniform, sponge forehead with cold water, administer ORS.",
            },
            "hi": {
                "summary": "विद्यालयों हेतु गंभीर हीटवेव चेतावनी। बच्चों में गर्मी सहन करने की क्षमता कम होती है। खुले मैदान की समस्त गतिविधियां तुरंत स्थगित करें।",
                "priority_alert": "खुले में खेलकूद व प्रार्थना सभाएं बंद करें — वाटर बेल लागू करें",
                "precautions": [
                    "सुबह 08:30 के बाद खुले मैदान में प्रार्थना सभा, खेलकूद और पीटी (PT) कक्षाएं पूरी तरह रद्द करें।",
                    "छात्रों को पानी पीने के लिए हर 45 मिनट में 'वाटर बेल' (जल घंटी) बजाएं।",
                    "कक्षाओं में पंखों और वेंटिलेशन की जांच करें; अधिक गर्म ऊपरी मंजिलों की कक्षाएं नीचे स्थानांतरित करें।",
                    "स्कूल बसों में पर्याप्त हवा की व्यवस्था रखें; किसी भी बच्चे को बस में अकेला न छोड़ें।",
                    "स्कूल डिस्पेंसरी में ओआरएस, ग्लूकोज और बर्फ की पट्टियां तैयार रखें।",
                ],
                "checklist": [
                    {"task": "सभी खेल और खुले मैदान की गतिविधियां रद्द करने का परिपत्र जारी करें", "timeframe": "प्रातः 07:30", "priority": "High"},
                    {"task": "हर 45 मिनट पर जलपान के लिए वाटर बेल बजाएं", "timeframe": "प्रत्येक 45 मिनट", "priority": "High"},
                    {"task": "सभी वाटर कूलरों और फिल्टरों का निरीक्षण करें", "timeframe": "प्रातः 08:00", "priority": "High"},
                    {"task": "चिकित्सा कक्ष में ओआरएस, बर्फ की थैलियां व थर्मामीटर सुसज्जित करें", "timeframe": "प्रातः 08:00", "priority": "High"},
                    {"task": "अभिभावकों को हल्के सूती कपड़े व पानी की बोतल भेजने हेतु संदेश भेजें", "timeframe": "पूर्व संध्या", "priority": "Medium"},
                ],
                "emergency_protocol": "बच्चे को चक्कर आने, उल्टी जैसा महसूस होने या बेहोशी पर तुरंत वातानुकूलित कमरे में लाएं। टाई-बेल्ट ढीले करें, माथे पर ठंडे पानी की पट्टी रखें और ओआरएस पिलाएं।",
            },
            "mr": {
                "summary": "शाळांसाठी तीव्र उष्णतेचा इशारा. लहान मुलांची उष्णता सहन करण्याची क्षमता कमी असते. मैदानावरील सर्व उपक्रम त्वरित थांबवा.",
                "priority_alert": "मैदानावरील खेळ व परिपाठ रद्द करा — दर ४५ मिनिटांनी 'वॉटर बेल' वाजवा",
                "precautions": [
                    "सकाळी ०८:३० नंतर उघड्या मैदानावर होणारी प्रार्थना, पीटी आणि खेळाचे तास पूर्णपणे रद्द करा.",
                    "विद्यार्थ्यांना पाणी पिण्याची आठवण करून देण्यासाठी दर ४५ मिनिटांनी 'वॉटर बेल' वाजवा.",
                    "वर्गातील पंखे आणि हवा खेळती राहण्याची खात्री करा; पत्र्यांच्या किंवा वरच्या मजल्यावरील वर्ग खाली हलवा.",
                    "शालेय बसमध्ये हवेशीर वातावरण ठेवा; कोणत्याही वाहनात विद्यार्थ्यांना एकटे सोडू नका.",
                    "शाळेच्या प्रथमोपचार कक्षात ओआरएस, ग्लुकोज आणि बर्फ सज्ज ठेवा.",
                ],
                "checklist": [
                    {"task": "मैदानावरील खेळ आणि व्यायाम बंद ठेवण्याचे परिपत्रक काढा", "timeframe": "सकाळी ०७:३०", "priority": "High"},
                    {"task": "दर ४५ मिनिटांनी पाणी पिण्यासाठी विशेष घंटा (वॉटर बेल) वाजवा", "timeframe": "दर ४५ मिनिटांनी", "priority": "High"},
                    {"task": "सर्व पिण्याच्या पाण्याच्या टाक्या व कुलर स्वच्छ असल्याची तपासणी करा", "timeframe": "सकाळी ०८:००", "priority": "High"},
                    {"task": "आजारी कक्षात ओआरएस, बर्फ व थर्मामीटरची उपलब्धता ठेवा", "timeframe": "सकाळी ०८:००", "priority": "High"},
                    {"task": "पालकांना सैल सुती गणवेश व पाण्याची मोठी बाटली देण्याबाबत सूचना पाठवा", "timeframe": "मागील संध्याकाळी", "priority": "Medium"},
                ],
                "emergency_protocol": "विद्यार्थ्याला चक्कर, मळमळ किंवा ग्लानी आल्यास ताबडतोब थंड खोलीत हलवा, कपडे सैल करा, कपाळावर पाण्याच्या घड्या ठेवा आणि ओआरएसचे पाणी द्या.",
            },
        },
        "RED": {
            "en": {
                "summary": "CRITICAL HEAT EMERGENCY for educational institutions. Extreme danger of pediatric heat shock. Immediate school schedule curtailment or closure mandated.",
                "priority_alert": "Red Alert: Close Afternoon Sessions — Suspend All Campus Presence by 11:30 AM",
                "precautions": [
                    "Curtail school operational hours to early morning session only (07:00 - 11:00 AM) or declare holiday per district collector directives.",
                    "Prohibit any student exposure to direct sunlight; keep all children in shaded, cooled indoor environments.",
                    "Dismiss classes by 11:00 AM before the critical solar peak window; ensure guarded, shaded transit home.",
                    "Strict prohibition against keeping children inside parked non-AC school buses.",
                    "Coordinate with local pediatric emergency clinics for heat-stroke rapid triage.",
                ],
                "checklist": [
                    {"task": "Enforce district collector order for morning-only hours (close by 11:00 AM)", "timeframe": "06:30", "priority": "High"},
                    {"task": "Mobilize school buses with window shades for early safe departure", "timeframe": "10:30", "priority": "High"},
                    {"task": "Mandatory final classroom sweep to confirm zero students remain in vehicles", "timeframe": "11:30", "priority": "High"},
                    {"task": "Station emergency medical car on campus with chilled electrolyte saline", "timeframe": "07:00 - 12:00", "priority": "High"},
                ],
                "emergency_protocol": "Pediatric heat shock: High fever, vomiting, convulsions, unconsciousness. Call 108 instantly. Immediately submerge child in lukewarm/cool water sponge. Fan vigorously. Pack neck and armpits with ice towels. Rush to ICU.",
            },
            "hi": {
                "summary": "विद्यालयों हेतु अत्यंत गंभीर आपातकाल (रेड अलर्ट)। बच्चों में हीट स्ट्रोक का जानलेवा जोखिम। 11:30 बजे से पूर्व विद्यालय बंद करने का आदेश।",
                "priority_alert": "रेड अलर्ट: दोपहर के सत्र स्थगित करें — सुबह 11:00 बजे तक छुट्टी करें",
                "precautions": [
                    "जिलाधिकारी के आदेशानुसार विद्यालय केवल सुबह के सत्र (07:00 - 11:00) में संचालित करें अथवा अवकाश घोषित करें।",
                    "किसी भी छात्र को धूप में बाहर न निकलने दें; सभी को पंखे व कूलर युक्त कमरों में ही रखें।",
                    "दोपहर की भीषण गर्मी से पूर्व सुबह 11:00 बजे तक सभी छात्रों को सुरक्षित घर रवाना करें।",
                    "पार्क की गई बसों में बच्चों को एक मिनट के लिए भी अकेला न छोड़ें।",
                    "निकटतम बाल रोग आपातकालीन वार्ड से सीधा संपर्क बनाए रखें।",
                ],
                "checklist": [
                    {"task": "प्रातः 11:00 बजे तक विद्यालय बंद करने का आदेश लागू करें", "timeframe": "प्रातः 06:30", "priority": "High"},
                    {"task": "छात्रों की सुरक्षित रवानगी हेतु छायादार बसों की व्यवस्था करें", "timeframe": "प्रातः 10:30", "priority": "High"},
                    {"task": "यह सुनिश्चित करें कि कोई भी बच्चा किसी वाहन में छूटा न रहे", "timeframe": "प्रातः 11:30", "priority": "High"},
                    {"task": "कैंपस में आपातकालीन चिकित्सा वाहन स्टैंडबाय रखें", "timeframe": "07:00 - 12:00", "priority": "High"},
                ],
                "emergency_protocol": "बाल हीट स्ट्रोक: तेज बुखार, उल्टी, बेहोशी या ऐंठन। तुरंत 108 डायल करें। बच्चे के कपड़े ढीले कर ठंडे पानी की पट्टी लगाएं। तुरंत बाल रोग आईसीयू अस्पताल ले जाएं।",
            },
            "mr": {
                "summary": "शाळांसाठी अति-तातडीची आणीबाणी (रेड अलर्ट). बालकांसाठी उष्माघाताचा तीव्र धोका. शाळा सकाळी ११:०० वाजता बंद करण्याचे आदेश.",
                "priority_alert": "रेड अलर्ट: दुपारची सत्रे रद्द करा — सकाळी ११:०० वाजता शाळा सोडा",
                "precautions": [
                    "जिल्हाधिकाऱ्यांच्या आदेशानुसार शाळा फक्त सकाळच्या सत्रात (०७:०० ते ११:००) भरवा किंवा सुट्टी जाहीर करा.",
                    "कोणत्याही विद्यार्थ्याला उन्हात बाहेर पडू देऊ नका; सर्व मुलांना पंखे असलेल्या थंड वर्गात ठेवा.",
                    "दुपारचे कडक ऊन पडण्यापूर्वी सकाळी ११:०० वाजता विद्यार्थ्यांना सुरक्षित घरी पाठवा.",
                    "उन्हात पार्क केलेल्या बसेसमध्ये विद्यार्थ्यांना कधीही एकटे बसवून ठेवू नका.",
                    "जवळच्या बालरुग्णालयाशी तात्काळ संपर्कात राहा.",
                ],
                "checklist": [
                    {"task": "सकाळी ११:०० वाजता शाळा सोडण्याचे परिपत्रक लागू करा", "timeframe": "सकाळी ०६:३०", "priority": "High"},
                    {"task": "विद्यार्थ्यांच्या सुरक्षित वाहतुकीसाठी बसेस सज्ज ठेवा", "timeframe": "सकाळी १०:३०", "priority": "High"},
                    {"task": "कोणताही विद्यार्थी बसमध्ये किंवा वर्गात राहिला नसल्याची खात्री करा", "timeframe": "सकाळी ११:३०", "priority": "High"},
                    {"task": "शाळेत आपत्कालीन रुग्णवाहिका किंवा वाहन तयार ठेवा", "timeframe": "०७:०० ते १२:००", "priority": "High"},
                ],
                "emergency_protocol": "उष्माघाताची गंभीर स्थिती: खूप ताप, उलट्या, झटके किंवा बेशुद्धी. तात्काळ १०८ वर फोन करा. मुलाला थंड पाण्याने पुसा, पंख्याखाली ठेवा आणि त्वरित रुग्णालयात दाखल करा.",
            },
        },
    },
    "older_adults": {
        "GREEN": {
            "en": {
                "summary": "Normal seasonal conditions. Maintain routine daily activities, regular hydration, and comfortable indoor ventilation.",
                "priority_alert": "Comfortable Seasonal Conditions — Maintain Daily Fluid Intake",
                "precautions": [
                    "Drink 1.5 to 2 liters of fluids throughout the day (water, coconut water, thin soups).",
                    "Take morning or evening walks before 08:30 AM or after 05:30 PM.",
                    "Keep living spaces well-ventilated with windows open during cooler morning hours.",
                    "Take prescribed daily medications on regular schedules.",
                ],
                "checklist": [
                    {"task": "Fill water jug and place by chair/bed", "timeframe": "Morning", "priority": "Medium"},
                    {"task": "Open windows for morning cross-ventilation", "timeframe": "07:00", "priority": "Low"},
                    {"task": "Review medication schedule with caregiver", "timeframe": "09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "If feeling slight dizzy or weak, rest comfortably in a chair, elevate legs slightly, and drink warm water or fresh lime water.",
            },
            "hi": {
                "summary": "सामान्य मौसमी मौसम। नियमित दिनचर्या, पर्याप्त पानी का सेवन और घर में हवादार वातावरण बनाए रखें।",
                "priority_alert": "सामान्य मौसम — नियमित रूप से पानी व तरल पदार्थ लेते रहें",
                "precautions": [
                    "दिनभर में 1.5 से 2 लीटर तरल पदार्थ (पानी, नारियल पानी, हल्का सूप) पिएं।",
                    "सुबह की सैर सुबह 08:30 से पहले या शाम 05:30 के बाद ही करें।",
                    "सुबह के समय खिड़कियां खोलकर ताजी हवा आने दें।",
                    "नियमित दवाइयां समय पर लें।",
                ],
                "checklist": [
                    {"task": "कुर्सी या बिस्तर के पास पीने के पानी का जग रखें", "timeframe": "प्रातःकाल", "priority": "Medium"},
                    {"task": "सुबह ताजी हवा के लिए खिड़कियां खोलें", "timeframe": "प्रातः 07:00", "priority": "Low"},
                    {"task": "नियमित दवाइयों की सूची की जांच करें", "timeframe": "प्रातः 09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "हल्का चक्कर आने पर पंखे के नीचे लेटें, पैरों को थोड़ा ऊंचा रखें और नींबू पानी या छाछ पिएं।",
            },
            "mr": {
                "summary": "हवामान सामान्य आहे. नेहमीची दिनचर्या सुरू ठेवा, पुरेसे पाणी प्या आणि घरात हवा खेळती ठेवा.",
                "priority_alert": "सामान्य हवामान — दिवसभरात नियमित पाणी व द्रवपदार्थ घ्या",
                "precautions": [
                    "दिवसभरात दीड ते दोन लिटर पाणी, नारळपाणी किंवा ताक घ्या.",
                    "सकाळचे चालणे सकाळी ०८:३० च्या आत किंवा संध्याकाळी ०५:३० नंतर ठेवा.",
                    "सकाळच्या वेळी खिडक्या उघडून घरात ताजी हवा येऊ द्या.",
                    "नेहमीची औषधे वेळेवर घ्या.",
                ],
                "checklist": [
                    {"task": "बसण्याच्या जागेजवळ पिण्याच्या पाण्याचा जग ठेवा", "timeframe": "सकाळ", "priority": "Medium"},
                    {"task": "घरात हवा खेळती ठेवण्यासाठी खिडक्या उघडा", "timeframe": "सकाळी ०७:००", "priority": "Low"},
                    {"task": "औषधे वेळेवर घेण्याबाबत खात्री करा", "timeframe": "सकाळी ०९:००", "priority": "Medium"},
                ],
                "emergency_protocol": "अशक्तपणा वाटल्यास शांतपणे झोपा, पाय थोडे उंच ठेवा आणि ताक किंवा लिंबू सरबत प्या.",
            },
        },
        "YELLOW": {
            "en": {
                "summary": "Heat watch active. Daytime heat rising. Elderly individuals should limit midday outdoor errands and increase fluid intake.",
                "priority_alert": "Heat Watch: Avoid Outdoor Errands 12:00 - 15:30 — Stay Hydrated",
                "precautions": [
                    "Avoid step-outs for groceries, temple visits, or bank work between 12:00 and 15:30.",
                    "Do not wait to feel thirsty; drink small cups of water every 45 minutes.",
                    "Wear light, loose-fitting cotton clothing and avoid synthetic fabrics.",
                    "Keep curtains drawn on west and south-facing windows from 11:00 AM onwards.",
                ],
                "checklist": [
                    {"task": "Complete all grocery/neighborhood errands before 10:30 AM", "timeframe": "Morning", "priority": "High"},
                    {"task": "Draw window curtains to block solar radiation", "timeframe": "11:00", "priority": "Medium"},
                    {"task": "Keep buttermilk, lemon water, or ORS prepared in kitchen", "timeframe": "11:30", "priority": "High"},
                    {"task": "Check in by phone with family member or neighbor", "timeframe": "13:00", "priority": "Medium"},
                ],
                "emergency_protocol": "Early heat strain: flushed skin, dry mouth, tiredness. Sponge face and neck with cool wet cloth, sit in front of fan, drink electrolyte water.",
            },
            "hi": {
                "summary": "हीट वॉच सक्रिय। तापमान बढ़ रहा है। बुजुर्ग दोपहर 12:00 से 15:30 के बीच धूप में बाहर न निकलें और पानी का सेवन बढ़ाएं।",
                "priority_alert": "हीट वॉच: दोपहर 12:00 से 15:30 के बीच धूप से बचें — तरल पदार्थ लें",
                "precautions": [
                    "बाजार, बैंक या मंदिर जाने जैसे काम सुबह 10:30 से पहले या शाम को करें।",
                    "प्यास लगने की प्रतीक्षा न करें; हर 45 मिनट पर थोड़ा पानी या छाछ पिएं।",
                    "हल्के, ढीले सूती कपड़े पहनें।",
                    "दोपहर में धूप वाली खिड़कियों के पर्दे बंद रखें ताकि कमरा ठंडा रहे।",
                ],
                "checklist": [
                    {"task": "सभी बाहरी कार्य सुबह 10:30 बजे से पहले पूरे करें", "timeframe": "प्रातःकाल", "priority": "High"},
                    {"task": "धूप रोकने के लिए खिड़कियों के पर्दे बंद करें", "timeframe": "प्रातः 11:00", "priority": "Medium"},
                    {"task": "नींबू पानी, छाछ या ओआरएस तैयार रखें", "timeframe": "11:30", "priority": "High"},
                    {"task": "परिवार के सदस्य को अपनी सेहत की जानकारी दें", "timeframe": "दोपहर 01:00", "priority": "Medium"},
                ],
                "emergency_protocol": "मुंह सूखने या थकान होने पर गीले कपड़े से चेहरा पोंछें, पंखे के पास बैठें और ओआरएस पिएं।",
            },
            "mr": {
                "summary": "हीट वॉच सक्रिय. उष्णता वाढत आहे. ज्येष्ठांनी दुपारी १२:०० ते १५:३० दरम्यान घराबाहेर पडणे टाळावे.",
                "priority_alert": "हीट वॉच: दुपारी १२:०० ते १५:३० उन्हात जाणे टाळा — भरपूर पाणी प्या",
                "precautions": [
                    "बाजार, देवदर्शन किंवा इतर कामे सकाळी १०:३० च्या आत किंवा संध्याकाळी करा.",
                    "तहान नसली तरी दर पाऊण तासाने थोडे पाणी किंवा ताक प्या.",
                    "सैल व हलके सुती कपडे वापरा.",
                    "दुपारच्या वेळी उन्हाकडील खिडक्यांचे पडदे लावून ठेवा.",
                ],
                "checklist": [
                    {"task": "बाहेरील सर्व कामे सकाळी १०:३० पूर्वी संपवा", "timeframe": "सकाळ", "priority": "High"},
                    {"task": "उष्णता रोखण्यासाठी खिडक्यांचे पडदे बंद करा", "timeframe": "सकाळी ११:००", "priority": "Medium"},
                    {"task": "ताक किंवा लिंबू सरबत तयार ठेवा", "timeframe": "सकाळी ११:३०", "priority": "High"},
                    {"task": "नातेवाईकांना किंवा शेजाऱ्यांना फोन करून प्रकृती कळवा", "timeframe": "दुपारी ०१:००", "priority": "Medium"},
                ],
                "emergency_protocol": "तोंड कोरडे पडल्यास किंवा चक्कर आल्यास ओल्या कापडाने मान व कपाळ पुसा आणि पंख्याखाली विश्रांती घ्या.",
            },
        },
        "ORANGE": {
            "en": {
                "summary": "Severe heat advisory for older adults and chronic patients. High thermal strain risk on cardiovascular and renal systems.",
                "priority_alert": "Stay Indoors in Cooled Rooms (11:00 - 17:00) — Monitor Medication & Hydration",
                "precautions": [
                    "Remain strictly indoors in the coolest room between 11:00 AM and 05:00 PM.",
                    "Consult doctor regarding fluid intake if prescribed diuretics or blood pressure medications.",
                    "Drink water regularly; do not wait to feel thirsty as thirst sensation diminishes with age.",
                    "Take cool sponge baths and use wet towels to lower body temperature.",
                    "Wear loose, light-colored cotton attire and avoid caffeinated or alcoholic beverages.",
                ],
                "checklist": [
                    {"task": "Close curtains/blinds on sun-facing windows to block radiant heat", "timeframe": "09:00", "priority": "High"},
                    {"task": "Keep 2 water bottles within arm's reach of your bed/chair", "timeframe": "Morning", "priority": "High"},
                    {"task": "Schedule daily morning check-in call with caregiver, family or neighbor", "timeframe": "10:00 & 16:00", "priority": "High"},
                    {"task": "Verify uninterrupted power or backup fan for peak afternoon hours", "timeframe": "11:00", "priority": "Medium"},
                    {"task": "Store essential medications in a cool, shaded spot away from direct heat", "timeframe": "Morning", "priority": "Medium"},
                ],
                "emergency_protocol": "Elderly heat crisis: Confusion, delirium, rapid shallow breathing, cessation of sweating. Immediate medical emergency. Call 108 or family doctor. Cool with wet sheets and fan immediately.",
            },
            "hi": {
                "summary": "वरिष्ठ नागरिकों व गंभीर रोगियों हेतु गंभीर चेतावनी। हृदय व गुर्दे पर अत्यधिक दबाव का जोखिम। दोपहर में घर से बाहर न निकलें।",
                "priority_alert": "दोपहर 11:00 से 17:00 तक घर के भीतर रहें — पर्याप्त पानी पिएं",
                "precautions": [
                    "सुबह 11:00 से शाम 17:00 के बीच घर के सबसे ठंडे कमरे में रहें, बाहर बिल्कुल न निकलें।",
                    "यदि बीपी या मूत्रवर्धक (diuretic) दवाएं ले रहे हैं, तो डॉक्टर की सलाह अनुसार पानी की मात्रा बनाए रखें।",
                    "प्यास का इंतजार न करें; उम्र बढ़ने के साथ प्यास का अहसास कम हो जाता है, इसलिए नियमित अंतराल पर पानी पिएं।",
                    "शरीर का तापमान कम करने के लिए दिन में दो बार ठंडे पानी से गीले कपड़े से बदन पोंछें।",
                    "चाय, कॉफी या शराब से बचें; नारियल पानी, छाछ और नींबू पानी का सेवन करें।",
                ],
                "checklist": [
                    {"task": "धूप वाली खिड़कियों के पर्दे बंद करें ताकि कमरे में गर्मी न आए", "timeframe": "प्रातः 09:00", "priority": "High"},
                    {"task": "बिस्तर या कुर्सी के पास पीने का पानी हमेशा रखें", "timeframe": "सुबह से", "priority": "High"},
                    {"task": "परिवार के सदस्य या पड़ोसी से दिन में कम से कम दो बार स्वास्थ्य जांच कॉल तय करें", "timeframe": "10:00 व 16:00", "priority": "High"},
                    {"task": "दवाइयों को सीधे धूप व गर्मी से दूर ठंडे स्थान पर रखें", "timeframe": "प्रातःकाल", "priority": "Medium"},
                ],
                "emergency_protocol": "भ्रम, बड़बड़ाना, अत्यधिक कमजोरी या सांस फूलने पर तुरंत 108 या पारिवारिक चिकित्सक को बुलाएं। तुरंत ठंडे पानी की पट्टी लगाएं।",
            },
            "mr": {
                "summary": "ज्येष्ठ नागरिक आणि दुर्धर आजार असलेल्या रुग्णांसाठी तीव्र उष्णतेचा इशारा. हृदय व मूत्रपिंडावर ताण येण्याची शक्यता. दुपारच्या वेळी घरातच राहा.",
                "priority_alert": "सकाळी ११:०० ते १७:०० घरातच राहा — नियमित पाणी प्या व औषधे वेळेवर घ्या",
                "precautions": [
                    "सकाळी ११:०० ते संध्याकाळी ०५:०० दरम्यान घरातल्या थंड खोलीत विश्रांती घ्या, उन्हात बाहेर पडू नका.",
                    "रक्तदाब किंवा इतर नियमित औषधे सुरू असल्यास डॉक्टरांच्या सल्ल्याने पाण्याचे प्रमाण ठरवा.",
                    "तहान लागण्याची वाट पाहू नका; वयोमानानुसार तहान कमी जाणवते, त्यामुळे दर तासाला थोडे पाणी प्या.",
                    "शरीराची उष्णता कमी करण्यासाठी थंड पाण्यात भिजवलेल्या पट्ट्यांनी अंग पुसा.",
                    "चहा किंवा कॉफीचे प्रमाण कमी करून ताक, नारळपाणी किंवा लिंबू सरबत घ्या.",
                ],
                "checklist": [
                    {"task": "उष्णता आत येऊ नये म्हणून खिडक्यांचे पडदे बंद करा", "timeframe": "सकाळी ०९:००", "priority": "High"},
                    {"task": "बसण्याच्या किंवा झोपण्याच्या जागेजवळ पाण्याची बाटली नेहमी ठेवा", "timeframe": "सकाळपासून", "priority": "High"},
                    {"task": "जवळचे नातेवाईक किंवा शेजाऱ्यांना दिवसातून दोनदा फोन करून प्रकृतीची माहिती द्या", "timeframe": "१०:०० व १६:००", "priority": "High"},
                    {"task": "सर्व आवश्यक औषधे थेट उन्हापासून दूर थंड जागेत ठेवा", "timeframe": "सकाळी", "priority": "Medium"},
                ],
                "emergency_protocol": "बोलताना अडखळणे, गोंधळून जाणे, श्वास घेण्यास त्रास किंवा बेशुद्धी आल्यास त्वरित १०८ रुग्णवाहिकेला फोन करा. रुग्णाला पंख्याखाली ठेवून ओल्या कापडाने थंड करा.",
            },
        },
        "RED": {
            "en": {
                "summary": "EXTREME HEAT EMERGENCY FOR OLDER ADULTS. Fatal heat stroke danger. Continuous caregiver supervision and actively cooled environment required.",
                "priority_alert": "Red Emergency: Strict Indoor Confinement in Air-Cooled Room — Continuous Supervision",
                "precautions": [
                    "Do NOT step outdoors under any circumstances between 10:30 AM and 06:00 PM.",
                    "Remain in an air-conditioned room or in front of an evaporative cooler with ice trays.",
                    "Caregivers must monitor body temperature, pulse, and mental alertness every 2 hours.",
                    "Apply cold damp compresses to neck, wrists, armpits, and groin if body feels hot.",
                    "Have an emergency vehicle and neighborhood physician's phone number on instant speed-dial.",
                ],
                "checklist": [
                    {"task": "Ensure AC or air cooler is operating with continuous power backup", "timeframe": "All Day", "priority": "High"},
                    {"task": "Check elder's alertness, pulse, and temperature every 2 hours", "timeframe": "Every 2h", "priority": "High"},
                    {"task": "Administer oral electrolytes or salted lime water in small sips", "timeframe": "Hourly", "priority": "High"},
                    {"task": "Keep ice packs and wet towels ready in freezer/refrigerator", "timeframe": "Morning", "priority": "High"},
                ],
                "emergency_protocol": "CRITICAL ELDER HEAT STROKE: Altered mental state, slurred speech, body temp > 39°C, dry burning skin. Call 108 instantly. Wrap in cold wet sheet, direct fan at maximum speed, rush to ICU.",
            },
            "hi": {
                "summary": "वरिष्ठ नागरिकों हेतु चरम लू आपातकाल (रेड अलर्ट)। जानलेवा हीट स्ट्रोक का अत्यधिक खतरा। निरंतर देखभाल और ठंडे कमरे में रहना अनिवार्य।",
                "priority_alert": "रेड अलर्ट: वातानुकूलित/कूलर वाले कमरे में रहें — धूप में बिल्कुल न निकलें",
                "precautions": [
                    "सुबह 10:30 से शाम 06:00 तक किसी भी परिस्थिति में घर से बाहर न निकलें।",
                    "कमरे में एसी (AC) या कूलर चलाएं और खिड़कियां पूरी तरह बंद रखें।",
                    "देखभालकर्ता हर 2 घंटे में नाड़ी की गति और शरीर के तापमान की जांच करें।",
                    "गर्मी लगने पर गर्दन, कलाइयों और बगल में ठंडे पानी की पट्टियां रखें।",
                    "आपातकालीन वाहन व डॉक्टर का नंबर फोन के स्पीड-डायल पर रखें।",
                ],
                "checklist": [
                    {"task": "कूलर या एसी का निरंतर चलना सुनिश्चित करें", "timeframe": "पूरे दिन", "priority": "High"},
                    {"task": "हर 2 घंटे में बुजुर्ग की चेतना व तापमान की जांच करें", "timeframe": "प्रत्येक 2 घंटे", "priority": "High"},
                    {"task": "हर घंटे ओआरएस या नारियल पानी घूंट-घूंट पिलाएं", "timeframe": "प्रति घंटे", "priority": "High"},
                    {"task": "फ्रिज में बर्फ की थैलियां व ठंडे तौलिए तैयार रखें", "timeframe": "प्रातःकाल", "priority": "High"},
                ],
                "emergency_protocol": "अत्यंत गंभीर: बेहोशी, भ्रम या शरीर अत्यधिक तपने पर तुरंत 108 पर कॉल करें। गीली चादर लपेटें, तेज पंखा चलाएं और बिना देरी किए आईसीयू ले जाएं।",
            },
            "mr": {
                "summary": "ज्येष्ठांसाठी अति-गंभीर आणीबाणी (रेड अलर्ट). उष्माघाताचा तीव्र धोका. थंड खोलीत राहणे आणि सतत काळजीवाहकाचे लक्ष असणे अनिवार्य.",
                "priority_alert": "रेड अलर्ट: वातानुकूलित किंवा कुलर असलेल्या खोलीतच राहा — उन्हात अजिबात पडू नका",
                "precautions": [
                    "सकाळी १०:३० ते संध्याकाळी ०६:०० पर्यंत कोणत्याही कारणास्तव घराबाहेर पडू नका.",
                    "घरातील कुलर किंवा एसी चालू ठेवा आणि उष्णता रोखा.",
                    "काळजीवाहकांनी दर २ तासांनी रुग्णाची प्रकृती, नाडी आणि तापमान तपासावे.",
                    "उष्णता जास्त वाटल्यास मान, काख आणि कपाळावर बर्फाच्या पट्ट्या ठेवा.",
                    "तातडीच्या रुग्णवाहिकेचा व डॉक्टरांचा फोन नंबर हाताशी ठेवा.",
                ],
                "checklist": [
                    {"task": "एसी किंवा कुलर अखंड चालू राहील याची खात्री करा", "timeframe": "दिवसभर", "priority": "High"},
                    {"task": "दर २ तासांनी ज्येष्ठ व्यक्तीचे तापमान व शुद्ध तपासा", "timeframe": "दर २ तासांनी", "priority": "High"},
                    {"task": "दर तासाला थोडे थोडे पाणी किंवा ओआरएस द्या", "timeframe": "दर तासाला", "priority": "High"},
                    {"task": "फ्रिजमध्ये बर्फ व ओले रुमाल सज्ज ठेवा", "timeframe": "सकाळी", "priority": "High"},
                ],
                "emergency_protocol": "तातडीची आणीबाणी: बेशुद्धी, गोंधळ, त्वचा खूप तापणे. त्वरित १०८ वर फोन करा. अंगावर गार पाण्याची चादर गुंडाळा आणि तात्काळ अतिदक्षता विभागात (ICU) दाखल करा.",
            },
        },
    },
    "event_organisers": {
        "GREEN": {
            "en": {
                "summary": "Normal seasonal weather for outdoor events. Standard crowd management and hydration logistics apply.",
                "priority_alert": "Standard Event Operations Permitted — Ensure Regular Water Stations",
                "precautions": [
                    "Maintain standard drinking water stalls every 150 meters.",
                    "Ensure adequate entry and exit widths to avoid crowd bottlenecks.",
                    "Provide basic shade canopies over ticketing counters and security gates.",
                    "Staff on-site first aid post with routine emergency supplies.",
                ],
                "checklist": [
                    {"task": "Verify drinking water dispenser refilling schedule", "timeframe": "2h prior", "priority": "Medium"},
                    {"task": "Inspect crowd entry/exit flow routes", "timeframe": "1h prior", "priority": "Medium"},
                    {"task": "Confirm basic first-aid kit is deployed", "timeframe": "Gate opening", "priority": "Low"},
                ],
                "emergency_protocol": "Standard first-aid: Treat minor cuts or dizziness with clean water and shaded rest.",
            },
            "hi": {
                "summary": "आयोजनों हेतु सामान्य मौसम। नियमित भीड़ प्रबंधन और पेयजल व्यवस्था पर्याप्त है।",
                "priority_alert": "सामान्य आयोजन संचालन — नियमित पेयजल स्टॉल सुनिश्चित करें",
                "precautions": [
                    "प्रत्येक 150 मीटर पर पीने के पानी के स्टॉल लगाएं।",
                    "भीड़ को नियंत्रित रखने के लिए प्रवेश व निकास द्वार खुले रखें।",
                    "टिकट काउंटर और सुरक्षा द्वारों पर छायादार शेड लगाएं।",
                    "प्राथमिक चिकित्सा कक्ष में आवश्यक दवाइयां उपलब्ध रखें।",
                ],
                "checklist": [
                    {"task": "पीने के पानी की आपूर्ति की जांच करें", "timeframe": "2 घंटे पूर्व", "priority": "Medium"},
                    {"task": "निकास द्वारों की चौड़ाई और सुरक्षा जांचें", "timeframe": "1 घंटे पूर्व", "priority": "Medium"},
                    {"task": "प्राथमिक चिकित्सा बॉक्स तैनात करें", "timeframe": "प्रारंभ", "priority": "Low"},
                ],
                "emergency_protocol": "चक्कर आने पर व्यक्ति को छाया में बैठाएं और पानी दें।",
            },
            "mr": {
                "summary": "कार्यक्रमांसाठी हवामान सामान्य आहे. नेहमीचे गर्दी नियंत्रण व पाण्याची सोय ठेवावी.",
                "priority_alert": "नेहमीचे कार्यक्रम नियोजन — पिण्याच्या पाण्याचे स्टॉल ठेवा",
                "precautions": [
                    "दर १५० मीटरवर पिण्याच्या पाण्याचे स्टॉल उभारा.",
                    "गर्दी कोंडू नये म्हणून प्रवेश व बाहेर पडण्याचे मार्ग मोकळे ठेवा.",
                    "तिकीट खिडकी व प्रवेशद्वारावर सावलीची व्यवस्था करा.",
                    "प्रथमोपचार केंद्रावर प्राथमिक औषधे सज्ज ठेवा.",
                ],
                "checklist": [
                    {"task": "पिण्याच्या पाण्याच्या उपलब्धतेची पाहणी करा", "timeframe": "२ तास आधी", "priority": "Medium"},
                    {"task": "बाहेर पडण्याच्या मार्गांची तपासणी करा", "timeframe": "१ तास आधी", "priority": "Medium"},
                    {"task": "प्रथमोपचार किट सज्ज ठेवा", "timeframe": "सुरू होताना", "priority": "Low"},
                ],
                "emergency_protocol": "चक्कर आल्यास सावलीत बसवून पाणी द्यावे.",
            },
        },
        "YELLOW": {
            "en": {
                "summary": "Heat watch active. Higher ambient temperatures expected. Upgrade shading and double hydration distribution points.",
                "priority_alert": "Heat Watch: Provide Covered Queue Canopies & Free Electrolyte Kiosks",
                "precautions": [
                    "Cover all spectator queue lines and waiting zones with UV-blocking shade mesh.",
                    "Increase free drinking water stations to every 75 meters.",
                    "Position portable water misting fans at high-density congregation points.",
                    "Announce hydration reminders over the public address system hourly.",
                ],
                "checklist": [
                    {"task": "Install shaded canopies over all open queue lines", "timeframe": "Morning", "priority": "High"},
                    {"task": "Double drinking water supply reserve for attendees", "timeframe": "2h prior", "priority": "High"},
                    {"task": "Deploy misting fans in main seating pavilions", "timeframe": "1h prior", "priority": "Medium"},
                    {"task": "Brief volunteers on identifying dehydrated attendees", "timeframe": "Pre-event briefing", "priority": "High"},
                ],
                "emergency_protocol": "Dehydrated attendee: Move to air-cooled first aid tent, provide oral rehydration salts, apply wet towels.",
            },
            "hi": {
                "summary": "हीट वॉच सक्रिय। तापमान में वृद्धि। दर्शकों की कतारों में छाया व पेयजल व्यवस्था दोगुनी करें।",
                "priority_alert": "हीट वॉच: कतारों में छायादार शेड लगाएं व निःशुल्क पानी उपलब्ध कराएं",
                "precautions": [
                    "दर्शकों की सभी कतारों और प्रवेश द्वारों पर छायादार शामियाने लगाएं।",
                    "प्रत्येक 75 मीटर पर ठंडे पेयजल के स्टॉल लगाएं।",
                    "अधिक भीड़ वाले स्थानों पर पानी की फुहार वाले (मिस्टिंग) पंखे लगाएं।",
                    "लाउडस्पीकर पर हर घंटे पानी पीने की घोषणाएं करें।",
                ],
                "checklist": [
                    {"task": "कतारों पर छायादार टेंट लगाएं", "timeframe": "प्रातःकाल", "priority": "High"},
                    {"task": "दर्शकों हेतु पेयजल का स्टॉक दोगुना करें", "timeframe": "2 घंटे पूर्व", "priority": "High"},
                    {"task": "मिस्टिंग पंखे चालू करें", "timeframe": "1 घंटे पूर्व", "priority": "Medium"},
                    {"task": "स्वयंसेवकों को डिहाइड्रेशन के लक्षणों की पहचान समझाएं", "timeframe": "ब्रीफिंग", "priority": "High"},
                ],
                "emergency_protocol": "थकान या निर्जलीकरण पर तुरंत ठंडे मेडिकल टेंट में लाएं और ओआरएस पिलाएं।",
            },
            "mr": {
                "summary": "हीट वॉच सक्रिय. तापमान वाढणार आहे. प्रेक्षकांच्या रांगांवर सावलीची व्यवस्था करा व पाण्याचे प्रमाण वाढवा.",
                "priority_alert": "हीट वॉच: रांगांवर सावलीचे मंडप लावा व मोफत थंड पाणी द्या",
                "precautions": [
                    "प्रवेशद्वारावरील सर्व रांगांवर सावलीचे कापड किंवा मंडप लावा.",
                    "दर ७५ मीटरवर मोफत पिण्याच्या पाण्याचे स्टॉल सुरू करा.",
                    "गर्दीच्या ठिकाणी पाणी फवारणी करणारे मिस्टिंग पंखे लावा.",
                    "ध्वनिक्षेपकावरून दर तासाला पाणी पिण्याच्या सूचना द्या.",
                ],
                "checklist": [
                    {"task": "सर्व रांगांवर सावलीची व्यवस्था पूर्ण करा", "timeframe": "सकाळ", "priority": "High"},
                    {"task": "पिण्याच्या पाण्याची साठवणूक दुप्पट करा", "timeframe": "२ तास आधी", "priority": "High"},
                    {"task": "मिस्टिंग पंखे सुरू करा", "timeframe": "१ तास आधी", "priority": "Medium"},
                    {"task": "स्वयंसेवकांना डिहायड्रेशन ओळखण्याचे प्रशिक्षण द्या", "timeframe": "बैठक", "priority": "High"},
                ],
                "emergency_protocol": "डिहायड्रेशन झालेल्या व्यक्तीस थंड मंडपात आणून ओआरएस व लिंबू सरबत द्यावे.",
            },
        },
        "ORANGE": {
            "en": {
                "summary": "High heat danger for public congregations and mass gatherings. Risk of mass dehydration, stampedes, and fainting episodes.",
                "priority_alert": "Mandate Shaded Pavilions, Misting Stations, & On-Site Emergency Triage",
                "precautions": [
                    "Erect shaded pavilions/tents with heat-reflective canopies over all gathering and queue areas.",
                    "Establish free drinking water refill kiosks every 50 meters with chilled water barrels.",
                    "Deploy misting fans and industrial evaporative coolers throughout seating zones.",
                    "Broadcast heatwave safety announcements in multiple languages every 30 minutes.",
                    "Position an on-site paramedic triage tent equipped with ice packs, ORS, and IV rehydration fluids.",
                ],
                "checklist": [
                    {"task": "Inspect continuous shade cover across waiting queues and open grounds", "timeframe": "3h prior to gates", "priority": "High"},
                    {"task": "Set up water replenishment stations with minimum 3 liters per attendee reserve", "timeframe": "2h prior", "priority": "High"},
                    {"task": "Position ambulance with paramedic and oxygen at secondary exit route", "timeframe": "On-site duration", "priority": "High"},
                    {"task": "Test PA sound system for scheduled multilingual heat announcements", "timeframe": "1h prior", "priority": "Medium"},
                    {"task": "Train 20 volunteer marshals in heat exhaustion first-aid identification", "timeframe": "Morning briefing", "priority": "High"},
                ],
                "emergency_protocol": "Crowd heat casualty: Immediately extract victim to air-conditioned medical tent. Place in recovery position, apply ice towels to neck and torso, initiate rapid hydration. Call dedicated emergency vehicle if recovery is delayed > 5 mins.",
            },
            "hi": {
                "summary": "सार्वजनिक आयोजनों एवं भीड़भाड़ वाले कार्यक्रमों हेतु उच्च जोखिम। सामूहिक निर्जलीकरण (डिहाइड्रेशन) व बेहोशी का खतरा।",
                "priority_alert": "छायादार टेंट, मिस्टिंग पंखे व ऑन-साइट एम्बुलेंस अनिवार्य करें",
                "precautions": [
                    "कतारों और बैठने के समस्त स्थानों पर धूप-रोधी छायादार वाटरप्रूफ टेंट लगाएं।",
                    "प्रत्येक 50 मीटर की दूरी पर निःशुल्क ठंडे पानी के वाटर डिस्पेंसर स्थापित करें।",
                    "जनसमूह वाले क्षेत्रों में मिस्टिंग (पानी की फुहार वाले) पंखे लगाएं।",
                    "लाउडस्पीकर पर हर 30 मिनट में धूप से बचाव के संदेश प्रसारित करें।",
                    "प्राथमिक चिकित्सा हेतु बर्फ, ओआरएस व पैरामेडिक्स युक्त मेडिकल टेंट अनिवार्य रखें।",
                ],
                "checklist": [
                    {"task": "प्रवेश द्वारों और कतारों पर पूर्ण छाया की जांच करें", "timeframe": "शुरू होने से 3 घंटे पूर्व", "priority": "High"},
                    {"task": "प्रति व्यक्ति कम से कम 3 लीटर पानी का रिजर्व स्टॉक सुनिश्चित करें", "timeframe": "2 घंटे पूर्व", "priority": "High"},
                    {"task": "आपातकालीन निकास मार्ग पर एम्बुलेंस मय मेडिकल टीम तैनात करें", "timeframe": "संपूर्ण कार्यक्रम", "priority": "High"},
                    {"task": "गर्मी से बचाव के लाउडस्पीकर संदेशों का पूर्वाभ्यास करें", "timeframe": "1 घंटे पूर्व", "priority": "Medium"},
                    {"task": "स्वयंसेवकों को हीट स्ट्रोक के प्राथमिक उपचार का प्रशिक्षण दें", "timeframe": "प्रातः ब्रीफिंग", "priority": "High"},
                ],
                "emergency_protocol": "बेहोश व्यक्ति को तुरंत भीड़ से निकालकर वातानुकूलित मेडिकल टेंट में लाएं। ठंडे पानी की पट्टी लगाएं और त्वरित चिकित्सा सहायता उपलब्ध कराएं।",
            },
            "mr": {
                "summary": "सार्वजनिक सभा व गर्दीच्या कार्यक्रमांसाठी अति-उष्णतेचा धोका. मोठ्या प्रमाणावर डिहायड्रेशन व चक्कर येण्याची शक्यता.",
                "priority_alert": "सावलीचे मंडप, मिस्टिंग पंखे आणि रुग्णवाहिका सज्ज ठेवणे बंधनकारक",
                "precautions": [
                    "रांगा आणि बसण्याच्या संपूर्ण जागेवर उष्णतारोधक सावलीचे मंडप उभारा.",
                    "प्रत्येक ५० मीटर अंतरावर मोफत थंड पिण्याच्या पाण्याचे स्टॉल उभारा.",
                    "गर्दीच्या ठिकाणी पाणी फवारणी करणारे (मिस्टिंग) मोठे पंखे लावा.",
                    "ध्वनिक्षेपकावरून दर ३० मिनिटांनी उन्हापासून काळजी घेण्याच्या सूचना द्या.",
                    "घटनास्थळी बर्फ, ओआरएस आणि वैद्यकीय पथकासह प्रथमोपचार केंद्र उभारा.",
                ],
                "checklist": [
                    {"task": "प्रवेशद्वार आणि रांगांवर पूर्ण सावली असल्याची खात्री करा", "timeframe": "सुरू होण्यापूर्वी ३ तास", "priority": "High"},
                    {"task": "प्रत्येक व्यक्तीमागे किमान ३ लिटर पिण्याच्या पाण्याची राखीव साठवणूक करा", "timeframe": "२ तास आधी", "priority": "High"},
                    {"task": "तातडीच्या बाहेर पडण्याच्या मार्गावर सुसज्ज रुग्णवाहिका तैनात ठेवा", "timeframe": "कार्यक्रम संपेपर्यंत", "priority": "High"},
                    {"task": "ध्वनिक्षेपकावरून मराठी, हिंदी व इंग्रजीतून सूचना देण्याची पूर्वतयारी करा", "timeframe": "१ तास आधी", "priority": "Medium"},
                    {"task": "उष्माघाताचे प्राथमिक उपचार करण्यासाठी स्वयंसेवकांना सूचना द्या", "timeframe": "सकाळची बैठक", "priority": "High"},
                ],
                "emergency_protocol": "गर्दीत कोणी चक्कर येऊन पडल्यास तात्काळ वातानुकूलित प्रथमोपचार मंडपात हलवा. डोक्यावर व मानेवर बर्फ ठेवा आणि त्वरित वैद्यकीय उपचार सुरू करा.",
            },
        },
        "RED": {
            "en": {
                "summary": "CRITICAL HEAT RISK FOR PUBLIC GATHERINGS. Extreme danger of mass heat casualties and stampedes. Postpone midday events or shift to late evening.",
                "priority_alert": "Red Emergency: Postpone Midday Outdoor Gatherings — Shift to Post-Sunset Only",
                "precautions": [
                    "Cancel or reschedule open-air mass gatherings scheduled between 11:00 AM and 05:00 PM.",
                    "If gathering cannot be cancelled, mandate 100% covered air-conditioned or heavy-duty cooled hangars.",
                    "Deploy multiple emergency cardiac ambulances with paramedics stationed on perimeter.",
                    "Free continuous cold bottled water and electrolyte distribution at all exits.",
                ],
                "checklist": [
                    {"task": "Issue formal event schedule postponement advisory to ticket holders", "timeframe": "24h prior", "priority": "High"},
                    {"task": "Station 3 cardiac life-support ambulances on site", "timeframe": "Full event", "priority": "High"},
                    {"task": "Operate 2 heavy-duty air-conditioned medical triage shelters", "timeframe": "Full event", "priority": "High"},
                ],
                "emergency_protocol": "Mass heat casualties: Trigger immediate emergency evacuation protocols. Route victims directly to shaded medical triage tents. Coordinate with municipal disaster control room.",
            },
            "hi": {
                "summary": "भीड़भाड़ वाले आयोजनों हेतु चरम आपातकाल (रेड अलर्ट)। जनसमूह में हीट स्ट्रोक का जानलेवा खतरा। दोपहर के आयोजन तुरंत स्थगित करें।",
                "priority_alert": "रेड अलर्ट: दोपहर के समस्त खुले आयोजन स्थगित करें — कार्यक्रम केवल शाम को रखें",
                "precautions": [
                    "सुबह 11:00 से शाम 05:00 के बीच खुले मैदान में कोई भी जनसभा या खेल आयोजन न करें।",
                    "यदि कार्यक्रम अनिवार्य हो तो केवल वातानुकूलित पंडालों में ही अनुमति दें।",
                    "स्थल पर डॉक्टरों व ऑक्सीजन युक्त कम से कम 3 एम्बुलेंस तैनात रखें।",
                    "सभी प्रवेश-निकास द्वारों पर ठंडे पानी और ओआरएस की असीमित आपूर्ति रखें।",
                ],
                "checklist": [
                    {"task": "दर्शकों को कार्यक्रम का समय बदलने की सूचना जारी करें", "timeframe": "24 घंटे पूर्व", "priority": "High"},
                    {"task": "स्थल पर 3 कार्डियक एम्बुलेंस तैनात करें", "timeframe": "पूरे समय", "priority": "High"},
                    {"task": "2 बड़े वातानुकूलित मेडिकल शेल्टर संचालित करें", "timeframe": "पूरे समय", "priority": "High"},
                ],
                "emergency_protocol": "सामूहिक आपातकाल: त्वरित निकासी योजना लागू करें। पीड़ितों को तत्काल वातानुकूलित मेडिकल टेंट में लाएं और जिला आपदा नियंत्रण कक्ष से संपर्क करें।",
            },
            "mr": {
                "summary": "सार्वजनिक कार्यक्रमांसाठी अति-गंभीर इशारा (रेड अलर्ट). गर्दीमध्ये मोठ्या प्रमाणात उष्माघाताचा धोका. दुपारचे कार्यक्रम रद्द करा.",
                "priority_alert": "रेड अलर्ट: दुपारचे सर्व मैदानी कार्यक्रम स्थगित करा — कार्यक्रम फक्त सूर्यास्तानंतर घ्या",
                "precautions": [
                    "सकाळी ११:०० ते संध्याकाळी ०५:०० दरम्यान खुल्या मैदानावर सभा किंवा सामने घेऊ नका.",
                    "अत्यंत आवश्यक असल्यास संपूर्ण वातानुकूलित मंडप उभारल्याशिवाय परवानगी देऊ नका.",
                    "घटनास्थळी डॉक्टरांसह किमान ३ सुसज्ज रुग्णवाहिका तैनात ठेवा.",
                    "प्रवेशद्वारांवर थंड पिण्याच्या पाण्याची आणि ओआरएसची अखंड व्यवस्था ठेवा.",
                ],
                "checklist": [
                    {"task": "कार्यक्रमाची वेळ बदलल्याचे जाहीर परिपत्रक काढा", "timeframe": "२४ तास आधी", "priority": "High"},
                    {"task": "किमान ३ कार्डिॲक रुग्णवाहिका सज्ज ठेवा", "timeframe": "कार्यक्रम संपेपर्यंत", "priority": "High"},
                    {"task": "२ मोठे वातानुकूलित प्रथमोपचार तंबू कार्यरत करा", "timeframe": "कार्यक्रम संपेपर्यंत", "priority": "High"},
                ],
                "emergency_protocol": "मोठ्या प्रमाणावर चक्कर आल्यास: तात्काळ आपत्कालीन बाहेर पडण्याचे मार्ग खुले करा. रुग्णांना प्रथमोपचार तंबूत हलवून पालिका नियंत्रण कक्षाशी संपर्क साधा.",
            },
        },
    },
    "municipal_officials": {
        "GREEN": {
            "en": {
                "summary": "Normal seasonal conditions across municipality. Routine civic water and sanitation operations.",
                "priority_alert": "Normal Civic Operations — Maintain Regular Water Supply Schedules",
                "precautions": [
                    "Maintain scheduled piped drinking water supply across all municipal zones.",
                    "Inspect public drinking water fountains (pyau) for cleanliness and functionality.",
                    "Monitor daily meteorological data from IMD regional observation stations.",
                    "Ensure civic hospitals have routine emergency stock of oral rehydration salts.",
                ],
                "checklist": [
                    {"task": "Review daily municipal reservoir storage levels", "timeframe": "08:00", "priority": "Low"},
                    {"task": "Verify public water kiosks in transit hubs", "timeframe": "10:00", "priority": "Medium"},
                    {"task": "Log IMD daily temperature bulletins", "timeframe": "16:00", "priority": "Low"},
                ],
                "emergency_protocol": "Routine hospital outpatient services: Treat seasonal dehydration cases via standard protocols.",
            },
            "hi": {
                "summary": "नगर निगम क्षेत्र में सामान्य मौसमी परिस्थितियां। नियमित जलापूर्ति और स्वच्छता सेवाएं सुचारु रखें।",
                "priority_alert": "सामान्य नागरिक संचालन — नियमित जलापूर्ति कार्यक्रम बनाए रखें",
                "precautions": [
                    "सभी वार्डों में निर्धारित समय पर पाइपलाइन से स्वच्छ जलापूर्ति सुनिश्चित करें।",
                    "सार्वजनिक प्याऊ और वाटर कूलरों की सफाई की जांच करें।",
                    "मौसम विभाग (IMD) के दैनिक बुलेटिन पर नजर रखें।",
                    "नगर निगम के अस्पतालों में ओआरएस का पर्याप्त भंडार रखें।",
                ],
                "checklist": [
                    {"task": "दैनिक जल भंडारण स्तर की समीक्षा करें", "timeframe": "प्रातः 08:00", "priority": "Low"},
                    {"task": "बस अड्डों व रेलवे स्टेशनों पर प्याऊ की जांच करें", "timeframe": "प्रातः 10:00", "priority": "Medium"},
                    {"task": "मौसम विभाग का तापमान बुलेटिन दर्ज करें", "timeframe": "शाम 16:00", "priority": "Low"},
                ],
                "emergency_protocol": "सामान्य अस्पताल सेवाएं: डिहाइड्रेशन के मरीजों का मानक उपचार करें।",
            },
            "mr": {
                "summary": "महानगरपालिका हद्दीत सामान्य हवामान. नियमित पाणीपुरवठा आणि नागरी सेवा सुरळीत सुरू ठेवाव्यात.",
                "priority_alert": "नेहमीचे नागरी कामकाज — नियमित पाणीपुरवठा वेळापत्रक पाळा",
                "precautions": [
                    "सर्व प्रभागांमध्ये वेळापत्रकानुसार नियमित पाणीपुरवठा करा.",
                    "सार्वजनिक पाणपोयांची स्वच्छता व पाण्याची तपासणी करा.",
                    "हवामान विभागाच्या दैनंदिन नोंदींवर लक्ष ठेवा.",
                    "पालिका दवाखान्यांमध्ये ओआरएसचा साठा ठेवा.",
                ],
                "checklist": [
                    {"task": "पाणी साठवण टाक्यांमधील पाणीसाठा तपासा", "timeframe": "सकाळी ०८:००", "priority": "Low"},
                    {"task": "बस स्थानक व मुख्य चौकातील पाणपोयांची पाहणी करा", "timeframe": "सकाळी १०:००", "priority": "Medium"},
                    {"task": "हवामान विभागाचा दैनंदिन अहवाल नोंदवा", "timeframe": "संध्याकाळी १६:००", "priority": "Low"},
                ],
                "emergency_protocol": "रुग्णालयातील नेहमीचे उपचार: नेहमीच्या पद्धतीनुसार उपचार करावेत.",
            },
        },
        "YELLOW": {
            "en": {
                "summary": "Heat watch bulletin issued. Temperature anomalies detected. Alert public health departments and prepare cooling infrastructure.",
                "priority_alert": "Heat Watch: Inspect Ward Drinking Kiosks & Alert Hospital Casualty Wards",
                "precautions": [
                    "Issue Heat Watch advisory bulletin to all municipal departments and schools.",
                    "Ensure round-the-clock water pressure at all public transit junctions and slum pockets.",
                    "Direct civic hospitals to stock additional IV fluids, ice packs, and ORS packets.",
                    "Inspect shaded areas at public bus stops and railway station concourses.",
                ],
                "checklist": [
                    {"task": "Issue municipal Heat Watch bulletin to zonal health officers", "timeframe": "09:00", "priority": "High"},
                    {"task": "Inspect water supply at high-density informal settlements", "timeframe": "11:00", "priority": "High"},
                    {"task": "Confirm emergency heat beds in civil hospital casualty", "timeframe": "12:00", "priority": "Medium"},
                    {"task": "Test city digital message hoardings for heat advisory display", "timeframe": "14:00", "priority": "Medium"},
                ],
                "emergency_protocol": "Alert primary health centers (PHCs) to document any early spikes in heat exhaustion visits.",
            },
            "hi": {
                "summary": "हीट वॉच बुलेटिन जारी। तापमान में वृद्धि। जन स्वास्थ्य विभाग को अलर्ट करें और पेयजल कियोस्क की जांच करें।",
                "priority_alert": "हीट वॉच: सभी वार्ड प्याऊ की जांच करें व अस्पतालों में आपातकालीन बेड तैयार रखें",
                "precautions": [
                    "सभी विभागों, स्कूलों और निर्माण स्थलों को हीट वॉच परामर्श जारी करें।",
                    "बस अड्डों, चौराहों और कच्ची बस्तियों में अतिरिक्त पेयजल उपलब्ध कराएं।",
                    "नगर निगम के अस्पतालों में आईवी फ्लूइड और ओआरएस की पर्याप्त आपूर्ति रखें।",
                    "बस स्टॉप पर छायादार शेड की व्यवस्था सुनिश्चित करें।",
                ],
                "checklist": [
                    {"task": "सभी जोनल स्वास्थ्य अधिकारियों को हीट वॉच अलर्ट भेजें", "timeframe": "प्रातः 09:00", "priority": "High"},
                    {"task": "घनी बस्तियों में पानी की आपूर्ति की समीक्षा करें", "timeframe": "प्रातः 11:00", "priority": "High"},
                    {"task": "अस्पतालों में हीट इमरजेंसी बेड तैयार रखें", "timeframe": "दोपहर 12:00", "priority": "Medium"},
                    {"task": "डिजिटल होर्डिंग्स पर गर्मी से बचाव के संदेश चलाएं", "timeframe": "दोपहर 14:00", "priority": "Medium"},
                ],
                "emergency_protocol": "प्राथमिक स्वास्थ्य केंद्रों को गर्मी से पीड़ित मरीजों का रिकॉर्ड रखने और त्वरित उपचार के निर्देश दें।",
            },
            "mr": {
                "summary": "हीट वॉच सूचना जारी. तापमानात वाढ होत आहे. आरोग्य विभागाला दक्षतेचा इशारा द्या व कुलिंग केंद्रांची तयारी ठेवा.",
                "priority_alert": "हीट वॉच: प्रभाग स्तरावर पाणपोया तपासा व रुग्णालयांना दक्षतेचा इशारा द्या",
                "precautions": [
                    "सर्व पालिका विभागांना व शाळांना हीट वॉचचे परिपत्रक पाठवा.",
                    "बस स्थानके आणि झोपडपट्ट्यांमध्ये पाण्याचा पुरवठा सुरळीत ठेवा.",
                    "पालिका रुग्णालयात सलाइन, बर्फ आणि ओआरएसचा अतिरिक्त साठा ठेवा.",
                    "बस थांब्यांवरील सावलीची पाहणी करा.",
                ],
                "checklist": [
                    {"task": "सर्व प्रभाग आरोग्य अधिकाऱ्यांना अलर्ट जारी करा", "timeframe": "सकाळी ०९:००", "priority": "High"},
                    {"task": "दाट वस्तीच्या भागात पाणीपुरवठ्याची पाहणी करा", "timeframe": "सकाळी ११:००", "priority": "High"},
                    {"task": "रुग्णालयात आपत्कालीन खाटा राखीव ठेवा", "timeframe": "दुपारी १२:००", "priority": "Medium"},
                    {"task": "डिजिटल फलकांवर उन्हापासून संरक्षणाचे संदेश सुरू करा", "timeframe": "दुपारी १४:००", "priority": "Medium"},
                ],
                "emergency_protocol": "प्राथमिक आरोग्य केंद्रांना उष्माघाताच्या रुग्णांवर त्वरित उपचार करण्याचे आदेश द्यावेत.",
            },
        },
        "ORANGE": {
            "en": {
                "summary": "High heatwave alert across municipal jurisdiction. Activate Heat Action Plan (HAP) Stage 2. Protect vulnerable urban pockets.",
                "priority_alert": "Activate City Heat Action Plan Level 2 — Open Public Cooling Shelters",
                "precautions": [
                    "Open air-conditioned municipal community centers, public libraries, and shaded transit hubs as public cooling shelters (10:00 - 18:00).",
                    "Deploy dedicated municipal water tankers to high-density informal settlements and construction clusters.",
                    "Ensure hospital casualty wards have designated 'Heat-Stroke Treatment Wards' with ice baths, cooling blankets, and IV fluids.",
                    "Coordinate with electricity distribution companies (DISCOMs) to guarantee uninterrupted power supply to hospitals and water pumping stations.",
                    "Issue localized public service announcements across city digital billboards, radio, and mobile messaging networks.",
                ],
                "checklist": [
                    {"task": "Convene emergency inter-agency Heat Action Plan taskforce meeting", "timeframe": "08:30", "priority": "High"},
                    {"task": "Activate public cooling centers across all municipal wards", "timeframe": "09:30", "priority": "High"},
                    {"task": "Dispatch emergency water tankers to water-scarce urban settlements", "timeframe": "10:00 & 14:00", "priority": "High"},
                    {"task": "Verify emergency cooling beds readiness in civil & municipal hospitals", "timeframe": "10:00", "priority": "High"},
                    {"task": "Broadcast SMS heatwave alert in local languages to registered citizens", "timeframe": "09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "Mass casualty heat emergency: Mobilize municipal disaster response teams. Open supplemental triage bays at primary health centers (PHCs). Requisition private hospital ICU capacity if heat-stroke admissions spike.",
            },
            "hi": {
                "summary": "नगर निगम क्षेत्र में गंभीर हीटवेव चेतावनी। हीट एक्शन प्लान (HAP) स्तर 2 सक्रिय करें। कमजोर बस्तियों की सुरक्षा सुनिश्चित करें।",
                "priority_alert": "हीट एक्शन प्लान स्तर 2 लागू करें — सार्वजनिक कूलिंग सेंटर खोलें",
                "precautions": [
                    "नागरिकों हेतु वातानुकूलित सामुदायिक भवन, पुस्तकालय और बस अड्डों पर सार्वजनिक कूलिंग शेल्टर खोलें (10:00 - 18:00)।",
                    "घनी बस्तियों, झुग्गी-झोपड़ियों और निर्माण स्थलों पर विशेष जल टैंकरों से जलापूर्ति सुनिश्चित करें।",
                    "सरकारी अस्पतालों में विशेष 'हीट स्ट्रोक वार्ड' सक्रिय करें जिसमें बर्फ स्नान, कूलिंग कंबल व दवाएं हों।",
                    "अस्पतालों व जल पंपिंग स्टेशनों पर 24 घंटे निर्बाध बिजली आपूर्ति हेतु विद्युत वितरण कंपनियों से समन्वय करें।",
                    "डिजिटल होर्डिंग्स, रेडियो व एसएमएस के माध्यम से स्थानीय भाषाओं में जनचेतावनी प्रसारित करें।",
                ],
                "checklist": [
                    {"task": "आपदा प्रबंधन और स्वास्थ्य अधिकारियों की आपात बैठक बुलाएं", "timeframe": "प्रातः 08:30", "priority": "High"},
                    {"task": "सभी वार्डों में सार्वजनिक कूलिंग शेल्टर सक्रिय करें", "timeframe": "प्रातः 09:30", "priority": "High"},
                    {"task": "जल संकट वाले इलाकों में आपातकालीन पेयजल टैंकर रवाना करें", "timeframe": "10:00 व 14:00", "priority": "High"},
                    {"task": "अस्पतालों में हीट स्ट्रोक बेड और दवाओं की उपलब्धता की समीक्षा करें", "timeframe": "प्रातः 10:00", "priority": "High"},
                    {"task": "नागरिकों को हिंदी व स्थानीय भाषा में अलर्ट एसएमएस भेजें", "timeframe": "प्रातः 09:00", "priority": "Medium"},
                ],
                "emergency_protocol": "सामूहिक आपातकाल: नगर आपदा राहत दल को तैनात करें। प्राथमिक स्वास्थ्य केंद्रों (PHC) में अतिरिक्त बेड लगाएं और आवश्यकता पड़ने पर निजी अस्पतालों से समन्वय करें।",
            },
            "mr": {
                "summary": "महानगरपालिका कार्यक्षेत्रात तीव्र उष्णतेची लाट. हीट ॲक्शन प्लॅन (HAP) टप्पा २ तात्काळ कार्यान्वित करा.",
                "priority_alert": "हीट ॲक्शन प्लॅन टप्पा २ लागू करा — सार्वजनिक कुलिंग सेंटर्स सुरू करा",
                "precautions": [
                    "नागरिकांसाठी पालिका समाजमंदिरे, अभ्यासिका व बस स्थानकांवर वातानुकूलित कुलिंग शेड सुरू करा (१०:०० ते १८:००).",
                    "दाट वस्त्या, झोपडपट्ट्या आणि बांधकाम वस्त्यांवर अतिरिक्त पाण्याच्या टँकर्सद्वारे पाणीपुरवठा करा.",
                    "सर्व पालिका व शासकीय रुग्णालयांत स्वतंत्र 'उष्माघात कक्ष' (Heat Stroke Ward) सज्ज ठेवा.",
                    "रुग्णालये व पाणीपुरवठा योजनांना अखंड वीजपुरवठा राहण्यासाठी महावितरणशी समन्वय साधा.",
                    "डिजिटल फलक, स्थानिक केबल व मोबाईल संदेशांद्वारे मराठीतून उष्णतेच्या लाटेचा इशारा प्रसारित करा.",
                ],
                "checklist": [
                    {"task": "आपत्ती व्यवस्थापन व आरोग्य विभागाची तातडीची बैठक घ्या", "timeframe": "सकाळी ०८:३०", "priority": "High"},
                    {"task": "सर्व प्रभागांत नागरिकांसाठी कुलिंग सेंटर्स खुली करा", "timeframe": "सकाळी ०९:३०", "priority": "High"},
                    {"task": "पाण्याची टंचाई असलेल्या भागात पाण्याचे टँकर्स पाठवा", "timeframe": "१०:०० व १४:००", "priority": "High"},
                    {"task": "रुग्णालयातील उष्माघात कक्षांची प्रत्यक्ष पाहणी करा", "timeframe": "सकाळी १०:००", "priority": "High"},
                    {"task": "नागरिकांना मराठीतून खबरदारीचे संदेश (SMS) पाठवा", "timeframe": "सकाळी ०९:००", "priority": "Medium"},
                ],
                "emergency_protocol": "सामूहिक आणीबाणी: आपत्कालीन व्यवस्थापन पथके तैनात करा. प्राथमिक आरोग्य केंद्रांवर अतिरिक्त खाटांची व्यवस्था करा आणि खाजगी रुग्णालयांना दक्षतेचा इशारा द्या.",
            },
        },
        "RED": {
            "en": {
                "summary": "EXTREME HEAT EMERGENCY ACROSS METROPOLITAN AREA. Full activation of Heat Action Plan Stage 3 (Red Alert). All civil resources mobilized.",
                "priority_alert": "Citywide Red Emergency: Activate Disaster Response & Mandate Midday Labor Suspension",
                "precautions": [
                    "Declare Municipal Heat Emergency under State Disaster Management Act.",
                    "Enforce mandatory suspension of direct sunlight manual labor (11:30 - 16:30) with labor enforcement flying squads.",
                    "Operate public cooling centers 24/7 with emergency paramedical and rehydration facilities.",
                    "Deploy maximum municipal water tanker fleet to un-piped vulnerable urban settlements.",
                    "Declare emergency priority power routing to hospitals and water pumping infrastructure.",
                ],
                "checklist": [
                    {"task": "Convene District Disaster Management Authority (DDMA) emergency command", "timeframe": "07:00", "priority": "High"},
                    {"task": "Deploy labor enforcement squads to enforce 11:30-16:30 work stoppage", "timeframe": "11:00", "priority": "High"},
                    {"task": "Activate 24-hour public cooling centers in all municipal wards", "timeframe": "08:00", "priority": "High"},
                    {"task": "Requisition private water tankers and emergency ambulances", "timeframe": "09:00", "priority": "High"},
                    {"task": "Coordinate daily heat casualty surveillance with all registered hospitals", "timeframe": "Every 4h", "priority": "High"},
                ],
                "emergency_protocol": "Catastrophic mass heatwave: Establish emergency field hospitals, requisition private cooling spaces, mobilize State Disaster Response Force (SDRF) for vulnerable population evacuations.",
            },
            "hi": {
                "summary": "संपूर्ण महानगर क्षेत्र में चरम लू आपातकाल (रेड अलर्ट)। हीट एक्शन प्लान स्तर 3 पूर्ण रूप से सक्रिय। समस्त नागरिक संसाधन तैनात।",
                "priority_alert": "शहरव्यापी रेड इमरजेंसी: आपदा प्रबंधन लागू करें व 11:30 से 16:30 श्रम रोकें",
                "precautions": [
                    "आपदा प्रबंधन अधिनियम के तहत नगर हीट इमरजेंसी घोषित करें।",
                    "सुबह 11:30 से शाम 16:30 तक खुले में शारीरिक श्रम पर पूर्ण प्रतिबंध लागू करने हेतु निरीक्षण दल भेजें।",
                    "सार्वजनिक कूलिंग सेंटर 24 घंटे चालू रखें जिसमें पैरामेडिकल स्टाफ व ओआरएस की व्यवस्था हो।",
                    "कच्ची बस्तियों और झुग्गियों में नगर निगम के समस्त जल टैंकरों को तैनात करें।",
                    "अस्पतालों और जल पंपिंग स्टेशनों को 24 घंटे निर्बाध बिजली देना अनिवार्य करें।",
                ],
                "checklist": [
                    {"task": "जिला आपदा प्रबंधन प्राधिकरण (DDMA) की आपात बैठक करें", "timeframe": "प्रातः 07:00", "priority": "High"},
                    {"task": "11:30 से 16:30 तक कार्य स्थगन लागू करने हेतु उड़नदस्ते तैनात करें", "timeframe": "प्रातः 11:00", "priority": "High"},
                    {"task": "सभी वार्डों में 24 घंटे कूलिंग सेंटर संचालित करें", "timeframe": "प्रातः 08:00", "priority": "High"},
                    {"task": "अस्पतालों में अतिरिक्त हीट स्ट्रोक आईसीयू बेड आरक्षित करें", "timeframe": "प्रातः 09:00", "priority": "High"},
                    {"task": "सभी अस्पतालों से हर 4 घंटे में हीट कैजुअल्टी रिपोर्ट लें", "timeframe": "हर 4 घंटे", "priority": "High"},
                ],
                "emergency_protocol": "आपदा राहत: नगर आपदा बल को सक्रिय करें, जरूरत पड़ने पर फील्ड अस्पताल बनाएं और कमजोर बस्तियों से बुजुर्गों को कूलिंग शेल्टरों में स्थानांतरित करें।",
            },
            "mr": {
                "summary": "महानगर क्षेत्रात अति-गंभीर उष्णता आणीबाणी (रेड अलर्ट). हीट ॲक्शन प्लॅन टप्पा ३ पूर्णपणे कार्यान्वित. सर्व नागरी यंत्रणा सज्ज.",
                "priority_alert": "शहरव्यापी रेड आणीबाणी: आपत्ती व्यवस्थापन लागू करा व ११:३० ते १६:३० उन्हातील कामे थांबवा",
                "precautions": [
                    "आपत्ती व्यवस्थापन कायद्यानुसार पालिका क्षेत्रात 'उष्णता आणीबाणी' जाहीर करा.",
                    "सकाळी ११:३० ते दुपारी १६:३० दरम्यान उन्हातील कामांवर सक्तीची बंदी घालण्यासाठी भरारी पथके नेमा.",
                    "नागरिकांसाठी सर्व प्रभागांत २४ तास कुलिंग सेंटर्स आणि वैद्यकीय पथके सज्ज ठेवा.",
                    "सर्व पालिका टँकर्स झोपडपट्ट्या व वंचित वस्त्यांमध्ये पाणीपुरवठ्यासाठी पाठवा.",
                    "रुग्णालये व पाणी उपसा केंद्रांना अखंड वीजपुरवठ्यासाठी महावितरणशी समन्वय साधा.",
                ],
                "checklist": [
                    {"task": "जिल्हा आपत्ती व्यवस्थापन प्राधिकरणाची तातडीची बैठक घ्या", "timeframe": "सकाळी ०७:००", "priority": "High"},
                    {"task": "११:३० ते १६:३० दरम्यान कामाची बंदी तपासण्यासाठी भरारी पथके रवाना करा", "timeframe": "सकाळी ११:००", "priority": "High"},
                    {"task": "सर्व प्रभागांत २४ तास कुलिंग सेंटर्स सुरू करा", "timeframe": "सकाळी ०८:००", "priority": "High"},
                    {"task": "खाजगी व पालिका रुग्णालयांतील अतिदक्षता खाटा आरक्षित ठेवा", "timeframe": "सकाळी ०९:००", "priority": "High"},
                    {"task": "प्रत्येक ४ तासांनी रुग्णालयातील उष्माघात रुग्णांचा आढावा घ्या", "timeframe": "दर ४ तासांनी", "priority": "High"},
                ],
                "emergency_protocol": "महाआपत्ती निवारण: तात्पुरते फील्ड रुग्णालय सुरू करा, राज्य आपत्ती प्रतिसाद दलाची (SDRF) मदत घ्या आणि दुर्बल घटकांना तातडीने सुरक्षित कुलिंग शेल्टरमध्ये हलवा.",
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Core Advisory Generator
# ---------------------------------------------------------------------------

def get_supported_roles() -> Dict[str, Any]:
    """Returns supported roles and metadata."""
    return ROLES_METADATA


def get_supported_languages() -> Dict[str, Any]:
    """Returns supported languages."""
    return SUPPORTED_LANGUAGES


def generate_fallback_advisory(
    city: str,
    date: str,
    role: str,
    language: str,
    risk_level: str,
    risk_score: float,
    forecast_tmax: float,
    forecast_tmin: float,
    departure: float,
    region_type: str,
) -> Dict[str, Any]:
    """Generates an authoritative, grounded advisory using verified NDMA/IMD rules."""
    role_key = role if role in NDMA_GROUNDED_RULES else "outdoor_workers"
    lang_key = language if language in ("en", "hi", "mr") else "en"

    # Match risk level, falling back gracefully
    risk_data = NDMA_GROUNDED_RULES.get(role_key, {})
    matched = None
    if risk_level in risk_data and lang_key in risk_data[risk_level]:
        matched = risk_data[risk_level][lang_key]
    else:
        for candidate_level in [risk_level, "ORANGE", "YELLOW", "RED", "GREEN"]:
            if candidate_level in risk_data and lang_key in risk_data[candidate_level]:
                matched = risk_data[candidate_level][lang_key]
                break
        if matched is None:
            matched = NDMA_GROUNDED_RULES["outdoor_workers"]["ORANGE"]["en"]

    role_title = ROLES_METADATA.get(role_key, {}).get("title", {}).get(lang_key, role_key)

    return {
        "city": city,
        "date": date,
        "role": role_key,
        "role_label": role_title,
        "language": lang_key,
        "risk_level": risk_level,
        "risk_score": round(float(risk_score), 2) if risk_score is not None else None,
        "forecast_tmax": round(float(forecast_tmax), 2) if forecast_tmax is not None else None,
        "forecast_tmin": round(float(forecast_tmin), 2) if forecast_tmin is not None else None,
        "departure": round(float(departure), 2) if departure is not None else None,
        "region_type": region_type,
        "model_used": "NDMA / IMD Grounded Rules Engine (Verified Baseline)",
        "is_generative": False,
        "advisory": {
            "summary": matched["summary"],
            "priority_alert": matched["priority_alert"],
            "precautions": matched["precautions"],
            "actionable_checklist": matched["checklist"],
            "emergency_protocol": matched["emergency_protocol"],
            "official_citations": [
                "National Disaster Management Authority (NDMA) National Guidelines for Preparation of Action Plan - Prevention and Management of Heat Wave",
                "India Meteorological Department (IMD) Operational Heat Action Plan & Heat Index Criteria",
                "Occupational Safety, Health and Working Conditions Code 2020",
            ],
        },
    }


def call_groq_advisory(
    city: str,
    date: str,
    role: str,
    language: str,
    risk_level: str,
    risk_score: float,
    forecast_tmax: float,
    forecast_tmin: float,
    departure: float,
    region_type: str,
    groq_api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Calls Groq AI API (LLaMA 3.3) with grounded context and returns structured JSON advisory."""
    api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.info("No Groq API key configured; using NDMA grounded rules fallback.")
        return None

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        role_info = ROLES_METADATA.get(role, ROLES_METADATA["outdoor_workers"])
        role_label = role_info["title"].get("en", role)
        target_lang = "English" if language == "en" else ("Hindi (हिन्दी in Devanagari script)" if language == "hi" else "Marathi (मराठी in Devanagari script)")

        system_prompt = f"""You are 'HeatWise AI', a world-class, authoritative Generative AI Heatwave Advisor.
Your objective is to convert verified weather alerts into personalized, highly practical, and actionable safety advisories.

STRICT GROUNDING RULES:
1. You MUST ground every recommendation strictly in the verified weather data provided below.
2. DO NOT hallucinate different temperatures or invent weather signals. The verified forecast values are absolute facts.
3. Align all advisories with official National Disaster Management Authority (NDMA) India and India Meteorological Department (IMD) standards.
4. Language Requirement: All output fields ('summary', 'priority_alert', 'precautions', 'task', 'emergency_protocol') MUST be written in natural, fluent, native-level {target_lang}.
5. You MUST return STRICTLY a JSON object matching this schema without any markdown wrapping or preamble:
{{
  "summary": "2-3 concise sentences contextualizing the exact temperature, departure, and target group risk",
  "priority_alert": "One sharp headline or imperative instruction for this role",
  "precautions": ["Precise precaution 1", "Precise precaution 2", "Precise precaution 3", "Precise precaution 4"],
  "actionable_checklist": [
    {{"task": "Actionable task description", "timeframe": "Time e.g. 07:00 or Morning", "priority": "High|Medium"}},
    {{"task": "Actionable task description", "timeframe": "Time e.g. 11:30", "priority": "High|Medium"}},
    {{"task": "Actionable task description", "timeframe": "Time e.g. Afternoon", "priority": "High|Medium"}},
    {{"task": "Actionable task description", "timeframe": "Time e.g. Daily", "priority": "High|Medium"}}
  ],
  "emergency_protocol": "Clear, practical steps if someone in this group suffers heat exhaustion or heat stroke",
  "official_citations": ["NDMA Heat Wave Guidelines", "IMD Heat Action Plan"]
}}"""

        user_content = f"""VERIFIED WEATHER & RISK CONTEXT:
- Monitored City: {city} ({region_type} region)
- Date of Forecast: {date}
- Forecast Maximum Temperature (Tmax): {forecast_tmax:.2f}°C
- Forecast Minimum Temperature (Tmin): {forecast_tmin:.2f}°C
- Departure from Normal: {'+' if departure >= 0 else ''}{departure:.2f}°C
- Validated Heat Risk Level: {risk_level} (Score: {risk_score:.0f}/100)
- Target User Group / Role: {role_label} ({role_info['description'].get('en')})
- Output Language: {target_lang}

Generate the grounded advisory and actionable checklist for this role now."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,  # Low temperature for strict factual adherence
            response_format={"type": "json_object"},
            max_tokens=1500,
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        role_title_local = role_info["title"].get(language, role_label)

        return {
            "city": city,
            "date": date,
            "role": role,
            "role_label": role_title_local,
            "language": language,
            "risk_level": risk_level,
            "risk_score": round(float(risk_score), 2) if risk_score is not None else None,
            "forecast_tmax": round(float(forecast_tmax), 2) if forecast_tmax is not None else None,
            "forecast_tmin": round(float(forecast_tmin), 2) if forecast_tmin is not None else None,
            "departure": round(float(departure), 2) if departure is not None else None,
            "region_type": region_type,
            "model_used": "LLaMA 3.3 70B Versatile (via Groq AI)",
            "is_generative": True,
            "advisory": parsed,
        }

    except Exception as e:
        logger.warning(f"Groq API call failed or encountered error: {e}. Falling back to grounded NDMA rules.")
        return None


def generate_advisory(
    city: str,
    date: str,
    role: str,
    language: str = "en",
    risk_level: str = "ORANGE",
    risk_score: float = 75.0,
    forecast_tmax: float = 40.0,
    forecast_tmin: float = 25.0,
    departure: float = 3.0,
    region_type: str = "plains",
    groq_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Main entry point: Generates personalized HeatWise AI advisory using Groq or grounded fallback."""
    # Attempt Groq Generative AI first
    groq_result = call_groq_advisory(
        city=city,
        date=date,
        role=role,
        language=language,
        risk_level=risk_level,
        risk_score=risk_score,
        forecast_tmax=forecast_tmax,
        forecast_tmin=forecast_tmin,
        departure=departure,
        region_type=region_type,
        groq_api_key=groq_api_key,
    )

    if groq_result is not None:
        return groq_result

    # Fallback to verified NDMA/IMD rules
    return generate_fallback_advisory(
        city=city,
        date=date,
        role=role,
        language=language,
        risk_level=risk_level,
        risk_score=risk_score,
        forecast_tmax=forecast_tmax,
        forecast_tmin=forecast_tmin,
        departure=departure,
        region_type=region_type,
    )
