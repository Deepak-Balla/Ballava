// App language. Menus, headings and main buttons are translated; recipe text stays in English for now.
// Anything without a translation falls back to English.
export const LANGS = [['en', 'English'], ['hi', 'हिन्दी'], ['te', 'తెలుగు'], ['ta', 'தமிழ்']];

const WORDS = {
  hi: {
    Cook: 'पकाएं', Plan: 'योजना', Track: 'रिकॉर्ड', Kitchen: 'रसोई', List: 'सूची', More: 'और',
    Family: 'परिवार', 'Ask Ballava': 'बल्लावा से पूछें', Account: 'खाता', Language: 'भाषा',
    "Today's menu": 'आज का मेन्यू', Breakfast: 'नाश्ता', Lunch: 'दोपहर का खाना', Dinner: 'रात का खाना',
    'Plan my week': 'मेरा हफ्ता बनाएं', 'Weekly plan': 'हफ्ते की योजना', 'Food diary': 'खाने की डायरी',
    'Cook now': 'अभी पकाएं', 'Almost there': 'बस थोड़ा और', 'Prep for tomorrow': 'कल की तैयारी',
    'Log a meal': 'खाना लिखें', 'What did you make today?': 'आज आपने क्या बनाया?', 'This week': 'इस हफ्ते',
    'Shopping list': 'खरीदारी की सूची', 'My kitchen': 'मेरी रसोई', 'Sign out': 'साइन आउट', 'Sign in': 'साइन इन',
    'One meal, many plates': 'एक खाना, सबकी थाली', 'Start cooking': 'पकाना शुरू करें', 'Family vote': 'परिवार का वोट',
  },
  te: {
    Cook: 'వంట', Plan: 'ప్రణాళిక', Track: 'రికార్డు', Kitchen: 'వంటగది', List: 'జాబితా', More: 'మరిన్ని',
    Family: 'కుటుంబం', 'Ask Ballava': 'బల్లావాను అడగండి', Account: 'ఖాతా', Language: 'భాష',
    "Today's menu": 'ఈ రోజు మెనూ', Breakfast: 'అల్పాహారం', Lunch: 'మధ్యాహ్న భోజనం', Dinner: 'రాత్రి భోజనం',
    'Plan my week': 'నా వారం ప్లాన్ చేయండి', 'Weekly plan': 'వారపు ప్రణాళిక', 'Food diary': 'ఆహార డైరీ',
    'Cook now': 'ఇప్పుడే వండండి', 'Almost there': 'దాదాపు సిద్ధం', 'Prep for tomorrow': 'రేపటికి సిద్ధం',
    'Log a meal': 'భోజనం నమోదు చేయండి', 'What did you make today?': 'ఈ రోజు ఏమి వండారు?', 'This week': 'ఈ వారం',
    'Shopping list': 'కొనుగోలు జాబితా', 'My kitchen': 'నా వంటగది', 'Sign out': 'సైన్ అవుట్', 'Sign in': 'సైన్ ఇన్',
    'One meal, many plates': 'ఒక వంట, అందరి పళ్లెం', 'Start cooking': 'వంట మొదలుపెట్టండి', 'Family vote': 'కుటుంబ ఓటు',
  },
  ta: {
    Cook: 'சமையல்', Plan: 'திட்டம்', Track: 'பதிவு', Kitchen: 'சமையலறை', List: 'பட்டியல்', More: 'மேலும்',
    Family: 'குடும்பம்', 'Ask Ballava': 'பல்லாவாவிடம் கேளுங்கள்', Account: 'கணக்கு', Language: 'மொழி',
    "Today's menu": 'இன்றைய மெனு', Breakfast: 'காலை உணவு', Lunch: 'மதிய உணவு', Dinner: 'இரவு உணவு',
    'Plan my week': 'என் வாரத்தை திட்டமிடு', 'Weekly plan': 'வாரத் திட்டம்', 'Food diary': 'உணவு நாட்குறிப்பு',
    'Cook now': 'இப்போது சமைக்கவும்', 'Almost there': 'கிட்டத்தட்ட தயார்', 'Prep for tomorrow': 'நாளைக்கான தயாரிப்பு',
    'Log a meal': 'உணவைப் பதிவு செய்', 'What did you make today?': 'இன்று என்ன சமைத்தீர்கள்?', 'This week': 'இந்த வாரம்',
    'Shopping list': 'வாங்கும் பட்டியல்', 'My kitchen': 'என் சமையலறை', 'Sign out': 'வெளியேறு', 'Sign in': 'உள்நுழை',
    'One meal, many plates': 'ஒரு சமையல், பல தட்டுகள்', 'Start cooking': 'சமைக்கத் தொடங்கு', 'Family vote': 'குடும்ப வாக்கு',
  },
};

let lang = 'en';
export function setLang(next) {
  lang = WORDS[next] ? next : 'en';
  try { document.documentElement.lang = lang; } catch { /* not in a browser */ }
}
export const t = text => WORDS[lang]?.[text] || text;
