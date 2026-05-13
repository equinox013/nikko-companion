// nikko-data.jsx — canned response patterns + APA7-formatted source library.

const NIKKO_SOURCES = {
  s_grounding: {
    title: 'Grounding techniques for distress',
    org: 'Beyond Blue',
    href: 'https://www.beyondblue.org.au/mental-health/anxiety/treatments-for-anxiety/anxiety-management-strategies',
    blurb: 'Practical, evidence-informed grounding strategies for moments of overwhelm — including the 5-4-3-2-1 sensory anchor and box breathing.',
    apa: 'Beyond Blue. (2024). Anxiety management strategies. Beyond Blue Ltd. Retrieved from https://www.beyondblue.org.au/mental-health/anxiety/treatments-for-anxiety/anxiety-management-strategies',
  },
  s_sleep: {
    title: 'Sleep hygiene fundamentals',
    org: 'Sleep Health Foundation (AU)',
    href: 'https://www.sleephealthfoundation.org.au/good-sleep-habits.html',
    blurb: 'Consistent wake times, light exposure in the morning, and reducing stimulants in the afternoon are first-line behavioural strategies.',
    apa: 'Sleep Health Foundation. (2023). Good-quality sleep: Healthy sleep habits. Sleep Health Foundation. https://www.sleephealthfoundation.org.au/good-sleep-habits.html',
  },
  s_rumination: {
    title: 'Working with rumination',
    org: 'Black Dog Institute',
    href: 'https://www.blackdoginstitute.org.au/resources-support/self-help/',
    blurb: 'Noticing the pattern, scheduled worry windows, and behavioural activation reduce ruminative loops over time.',
    apa: 'Black Dog Institute. (2024). Self-help resources for rumination and worry. Black Dog Institute, UNSW Sydney. https://www.blackdoginstitute.org.au/resources-support/self-help/',
  },
  s_values: {
    title: 'Values clarification (ACT)',
    org: 'Australian Psychological Society',
    href: 'https://psychology.org.au/for-the-public/psychology-topics',
    blurb: 'Acceptance and Commitment Therapy approaches use values as a compass when motivation and mood are low.',
    apa: 'Australian Psychological Society. (2023). Acceptance and Commitment Therapy: An overview for the public. APS. https://psychology.org.au/for-the-public/psychology-topics',
  },
  s_breath: {
    title: 'Slow paced breathing & vagal tone',
    org: 'University of Melbourne',
    href: 'https://findanexpert.unimelb.edu.au/',
    blurb: 'Exhale-extended breathing at ~6 breaths/min reliably engages parasympathetic activity within minutes.',
    apa: 'Laborde, S., Allen, M. S., Borges, U., Dosseville, F., Hosang, T. J., Iskra, M., Mosley, E., Salvotti, C., Spolverato, L., Zammit, N., & Javelle, F. (2022). Effects of voluntary slow breathing on heart rate and heart rate variability: A systematic review and meta-analysis. Neuroscience & Biobehavioral Reviews, 138, 104711. https://doi.org/10.1016/j.neubiorev.2022.104711',
  },
  s_loneliness: {
    title: 'Loneliness and social connection',
    org: 'Ending Loneliness Together (AU)',
    href: 'https://endingloneliness.com.au/',
    blurb: 'Frequent, low-stakes contact with familiar people predicts wellbeing more strongly than rare, high-intensity contact.',
    apa: 'Ending Loneliness Together. (2023). State of the nation report: Social connection in Australia 2023. Ending Loneliness Together. https://endingloneliness.com.au/',
  },
  s_crisis_au: {
    title: 'Australian crisis support directory',
    org: 'Head to Health · Department of Health',
    href: 'https://www.headtohealth.gov.au/',
    blurb: 'Lifeline 13 11 14, Beyond Blue 1300 22 4636, 13YARN 13 92 76, and emergency services on 000.',
    apa: 'Australian Government Department of Health and Aged Care. (2024). Head to Health: Crisis support directory. Commonwealth of Australia. https://www.headtohealth.gov.au/',
    safety: true,
  },
};

const NIKKO_OPENING = {
  text:
    "Hi — I'm Nikko. There's no script and nothing to perform here. " +
    "If you'd like, you can tell me what's been on your mind, " +
    "or pick one of the prompts below. I'll move at your pace.",
  emotion: 'calm',
};

const NIKKO_SUGGESTIONS = [
  "I haven't been sleeping well",
  "My head is loud today",
  "I just want to vent for a minute",
  "I'm not sure why I feel off",
];

const NIKKO_PATTERNS = [
  {
    match: /\b(suicid\w*|kill(ing)? myself|end it|hurt(ing)? myself|self.?harm\w*|not safe|don'?t feel safe|want to die|wanna die|don'?t want to be here|don'?t want to live|in danger)\b/i,
    safety: true,
    chunks: [
      { emotion: 'care', text:
        "Thank you for telling me. I'm here, and I'm taking what you said seriously. " +
        "You don't have to explain or justify any of it before getting support." },
      // REQ-300-RS1: all four baseline resources MUST appear in the crisis response text.
      // REQ-300-RS2: demographic-specific resources surface via the SafetyBanner expandable — not here.
      { emotion: 'care', text:
        "If you're in immediate danger, please call **000**. " +
        "**Lifeline (13 11 14)** is available 24/7. " +
        "**Beyond Blue (1300 22 4636)** and the **Suicide Call Back Service (1300 659 467)** " +
        "are also available any time. You can find more tailored support options in the banner above.[^s_crisis_au]" },
      { emotion: 'listen', text:
        "If you'd like to stay with me for a moment too, that's okay. " +
        "Would it help to tell me a little about what today has felt like?" },
    ],
  },
  {
    match: /\b(sleep\w*|insomnia|tired|can'?t sleep|exhausted|wake\w*( up)?|awake|restless\w*)\b/i,
    chunks: [
      { emotion: 'listen', text:
        "Sleep that won't come is exhausting in its own right — and noticing it is a real thing, not a small one." },
      { emotion: 'search', text:
        "A few patterns tend to help over a couple of weeks rather than overnight: keeping a consistent wake time, " +
        "getting outdoor light within an hour of waking, and easing back on caffeine after early afternoon.[^s_sleep] " +
        "Slow, exhale-extended breathing for a few minutes before bed can also lower the alarm signal in the body.[^s_breath]" },
      { emotion: 'speak', text:
        "Before any of that though — what does your night usually look like? " +
        "I want to understand the shape of it before suggesting anything." },
    ],
  },
  {
    match: /\b(loud|rac\w+|overthink\w*|rumin\w*|spiral\w*|can'?t stop thinking|stuck in my head|head is loud|mind is loud|noisy)\b/i,
    chunks: [
      { emotion: 'listen', text:
        "A loud head is tiring. It's also doing something — usually trying to keep you safe — even when it doesn't feel that way." },
      { emotion: 'search', text:
        "One thing that helps some people is noticing the loop instead of trying to win the argument inside it. " +
        "Naming it (\"this is my mind ruminating\") plus a small, physical anchor — " +
        "feet on the floor, five things you can see — can take the edge off without trying to silence the thoughts.[^s_grounding][^s_rumination]" },
      { emotion: 'speak', text:
        "Would you like to try a 60-second grounding step together, or would you rather just talk for a bit?" },
    ],
  },
  {
    match: /\b(vent\w*|rant\w*|just want to talk|need to talk|listen to me|wanna talk)\b/i,
    chunks: [
      { emotion: 'listen', text:
        "Of course. I'm not going to interrupt you or steer this anywhere — take whatever space you need." },
      { emotion: 'speak', text:
        "Whenever you're ready, I'm listening." },
    ],
  },
  {
    match: /\b(lonely|loneliness|alone|isolat\w*|no one|nobody|by myself|no friends)\b/i,
    chunks: [
      { emotion: 'care', text:
        "Loneliness is heavier than people give it credit for, especially when it's quiet around you." },
      { emotion: 'search', text:
        "A small thing that's been studied a fair bit: brief, low-stakes contact with people you already know — " +
        "a short message, a coffee, a walk — tends to lift wellbeing more reliably than rare, big social events.[^s_loneliness]" },
      { emotion: 'listen', text:
        "Is there one person you haven't talked to in a while who feels low-effort to reach out to?" },
    ],
  },
  {
    match: /\b(off|flat|numb\w*|nothing|empty|don'?t care|whatever|feel weird|feel strange|feel odd)\b/i,
    chunks: [
      { emotion: 'listen', text:
        "Feeling off without a clear reason is its own kind of fog — and it's allowed to be vague." },
      { emotion: 'search', text:
        "Sometimes the move isn't to figure out the cause first, but to do one small thing tied to what you usually care about — " +
        "even a tiny version of it. The mood often follows the action, not the other way round.[^s_values]" },
      { emotion: 'speak', text:
        "If today were a quietly good day, what's one thing — really small — that would have happened in it?" },
    ],
  },
  {
    match: /\b(anxious|anxiety|panic\w*|nervous|on edge|worr\w+|scared|stress\w*|overwhelm\w*)\b/i,
    chunks: [
      { emotion: 'care', text:
        "Anxiety has a way of arriving with no schedule. I'm glad you said something." },
      { emotion: 'search', text:
        "If your body feels switched on right now, slow exhale-led breathing — say four in, six or eight out — " +
        "for a couple of minutes can take the volume down a notch.[^s_breath] " +
        "It's not a fix; it just gives you a little more room to think." },
      { emotion: 'listen', text:
        "Is the anxiety attached to something specific today, or more of a general hum?" },
    ],
  },
  {
    match: /\b(thank\w*|thanks|appreciate\w*|grateful)\b/i,
    chunks: [
      { emotion: 'speak', text:
        "You're welcome. Take what's useful, leave what isn't." },
      { emotion: 'calm', text:
        "I'll be here whenever you'd like to come back to it." },
    ],
  },
];

const NIKKO_FALLBACK = {
  chunks: [
    { emotion: 'listen', text:
      "I hear you. Could you tell me a bit more about what that's been like for you?" },
    { emotion: 'speak', text:
      "There's no right way to say it — whatever comes out is fine." },
  ],
};

function matchNikkoPattern(text) {
  for (const p of NIKKO_PATTERNS) {
    if (p.match.test(text)) return p;
  }
  return NIKKO_FALLBACK;
}

Object.assign(window, {
  NIKKO_SOURCES, NIKKO_OPENING, NIKKO_SUGGESTIONS,
  NIKKO_PATTERNS, NIKKO_FALLBACK, matchNikkoPattern,
});
