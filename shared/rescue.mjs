// Bachao Mode: quick, honest fixes for everyday kitchen accidents.
// "myth" notes call out popular tricks that don't really work.

export const RESCUES = [
  {
    id: 'too_salty', title: 'Too much salt', keywords: 'salty salt namak zyada',
    fixes: [
      'Dilute it: add more of the base without salt (water or stock for dal and rasam; tomato purée, coconut milk or a little cream for gravies).',
      'Add more of the main ingredient: extra boiled dal, extra vegetables or more rice to spread the salt out.',
      'Balance the taste with a squeeze of lemon or a pinch of sugar or jaggery. It masks saltiness but doesn\'t remove it.',
      'For dry sabzi, serve it with plain curd, unsalted roti or rice.',
    ],
    myth: 'The "drop in a raw potato" trick barely works. The potato soaks up salty water, not salt. Diluting is what actually fixes it.',
  },
  {
    id: 'too_spicy', title: 'Too spicy', keywords: 'spicy hot teekha mirchi chilli',
    fixes: [
      'Add fat or dairy: a spoon of ghee or butter, curd, cream, milk or coconut milk (dairy calms chilli heat best).',
      'Add bulk: more tomato, onion, boiled potato or dal.',
      'A pinch of sugar or jaggery and a squeeze of lemon help balance it.',
      'Serve with curd, raita or plain rice. Take out a separate mild portion for kids before fixing the rest.',
    ],
  },
  {
    id: 'too_sour', title: 'Too sour or tangy', keywords: 'sour khatta tangy tamarind',
    fixes: [
      'Add a pinch of sugar or jaggery and taste again.',
      'Add a little cream, coconut milk or more of the base to soften it.',
      'If tomatoes taste raw and sharp, cook them longer until oil separates.',
    ],
  },
  {
    id: 'too_sweet', title: 'Too sweet', keywords: 'sweet meetha sugar',
    fixes: [
      'For savoury dishes: add lemon juice, a pinch of salt or a little chilli.',
      'Add more of the unsweetened base to dilute it.',
      'For desserts: add unsweetened milk (kheer) or more roasted sooji with a little ghee (halwa).',
    ],
  },
  {
    id: 'too_watery', title: 'Gravy or dal too watery', keywords: 'watery thin runny patla',
    fixes: [
      'Simmer uncovered, stirring, until it reduces.',
      'Mash a little of the dal or a boiled potato into it.',
      'Stir in 1 tbsp besan roasted in a little oil, or 1 tbsp cashew or peanut paste, then simmer for 3-4 minutes.',
    ],
  },
  {
    id: 'too_thick', title: 'Too thick', keywords: 'thick gaadha dense',
    fixes: [
      'Add hot water a little at a time and simmer (cold water can dull the flavour).',
      'Taste and adjust the salt after thinning.',
    ],
  },
  {
    id: 'burnt_bottom', title: 'Burnt at the bottom', keywords: 'burnt burned jal gaya smoky stuck',
    fixes: [
      'Take it off the heat right away. Do NOT stir; stirring spreads the burnt taste.',
      'Spoon the unburnt top part into a clean pot without scraping the bottom.',
      'Taste it. A fresh tadka of ghee, cumin and garlic covers a slight smoky note.',
      'Soak the burnt pot in hot water with a spoon of baking soda before scrubbing.',
    ],
    safety: 'If the whole dish tastes bitter and burnt, it is better to start again than to eat it.',
  },
  {
    id: 'rice_mushy', title: 'Rice turned mushy', keywords: 'rice mushy sticky gila',
    fixes: [
      'Spread it on a plate to let the steam escape and the grains firm up.',
      'Turn it into something where soft rice is good: khichdi, curd rice, pongal, rice kheer or cutlets.',
      'Next time, use less water: about 1.5-1.75 cups per cup of soaked basmati.',
    ],
  },
  {
    id: 'rice_hard', title: 'Rice undercooked or hard', keywords: 'rice hard raw kachcha uncooked',
    fixes: [
      'Sprinkle 2-4 tbsp hot water over the rice, cover tightly, and steam on the lowest heat for 5-10 minutes.',
      'Don\'t stir; it breaks the grains.',
    ],
  },
  {
    id: 'curdled', title: 'Curd or milk split in the gravy', keywords: 'curdled split phat gaya kadhi broke',
    fixes: [
      'Take it off the heat. Blend with a hand blender or whisk hard; it often comes back together.',
      'Whisk in a spoon of cream or cashew paste to smooth it out.',
      'Next time: whisk curd with a spoon of besan, add it on low heat, and keep stirring until it boils.',
    ],
  },
  {
    id: 'bland', title: 'Tastes bland', keywords: 'bland pheeka no taste tasteless',
    fixes: [
      'Salt first. Most "bland" food just needs salt.',
      'Then acid: lemon, amchur or a little tamarind wakes up flavours.',
      'Finish with a pinch of garam masala, kasuri methi or a fresh tadka.',
    ],
  },
  {
    id: 'raw_masala', title: 'Masala tastes raw', keywords: 'raw masala kachcha smell powdery',
    fixes: [
      'Keep cooking on medium until oil separates at the edges.',
      'If it starts sticking, add 2 tbsp water and keep cooking.',
    ],
  },
  {
    id: 'too_oily', title: 'Too much oil', keywords: 'oily greasy tel',
    fixes: [
      'Let it rest for 2 minutes, then skim the oil off the top with a spoon.',
      'Lay a paper towel gently on the surface to soak up oil, then lift it off.',
      'Add more base (tomato, dal or vegetables) to balance it.',
    ],
  },
  {
    id: 'dough', title: 'Dough too sticky or too dry', keywords: 'dough atta sticky dry hard',
    fixes: [
      'Sticky: add atta 1 spoon at a time, oil your hands, and rest the dough for 15 minutes.',
      'Dry or cracking: wet your hands and knead again; repeat until soft.',
      'Always rest the dough for 15-20 minutes. It makes softer rotis.',
    ],
  },
  {
    id: 'bitter', title: 'Tastes bitter', keywords: 'bitter kadwa',
    fixes: [
      'If garlic or spices burnt in the tadka: throw the tadka away and start it again. You can\'t mask it.',
      'For karela or methi: a little jaggery, tamarind or lemon balances the bitterness.',
    ],
  },
  {
    id: 'safe', title: 'Is it still safe to eat?', keywords: 'safe spoiled stale expired kharab smell',
    fixes: [
      'Throw it away if it smells sour or off, looks slimy, fizzes, or has any mould.',
      'Cooked food left at room temperature for more than 2 hours should not be eaten later.',
      'Refrigerated leftovers: eat within 1-2 days; reheat until steaming hot all the way through.',
      'Cooked rice is a special risk: refrigerate it within 1-2 hours, and reheat it only once.',
    ],
    safety: 'When in doubt, throw it out. No dish is worth food poisoning.',
  },
];
