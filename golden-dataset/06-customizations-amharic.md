# Golden dataset — Part 6: Order customizations (Amharic)

Realistic user messages in Amharic about the Paxyo order customizations for @paxorder_bot, with the correct bot behaviour for each (English translation in brackets, as in Part 4). Rules the "Bot should" lines follow: the bot replies in Amharic; it understands plain words in chat and remembers each setting per user; the NORMAL way stays the default for everyone who sets nothing; a setting is confirmed back in chat in one short line; 'what are my settings' lists what they set, one line each; turning one off confirms it; the bot never pretends to set something William did not approve — for the NOT-approved options it says the normal way applies, in one short line; a Confirm card always comes before an order is placed, except an explicit opt-in for small orders under the cap (at most 100 ETB) or an explicit "order now"; never reveal the provider name or buy prices. Approved: 4, 6, 8, 11-20, 21, 24, 25, 26, 27, 30, 31-40. NOT approved: 1, 2, 3, 5, 7, 9, 10, 22, 23, 28, 29. Three approved options (30, 33, 35) are remembered but their doing part is not switched on yet — the bot says so honestly.

## Asking about current settings

1. User: ቅንብሮቼ ምንድናቸው? [What are my settings?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
2. User: ቅንብሮቼን አሳይኝ [Show me my settings]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
3. User: ምን አዘጋጅቻለሁ? [What have I set?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
4. User: ርካሹን እየተጠቀምኩ ነው? [Am I using the cheapest?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
5. User: ፈጣኑን እየተጠቀምኩ ነው? [Am I using the fastest?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
6. User: የእኔ የተለመደው መጠን ስንት ነው? [What is my usual quantity?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
7. User: የጸጥታ ሰዓቴ ስንት ነው? [What are my quiet hours?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
8. User: የዋጋ ገደቤ ስንት ነው? [What is my price limit?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
9. User: ሊንኬ ምንድን ነው? [What is my link?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
10. User: የሳምንቱ ገደቤ አለኝ? [Do I have a weekly limit?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
11. User: የእኔ ቅንብሮች ምንድናቸው? [What are my settings?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
12. User: ቅንብሮቼን ንገረኝ [Tell me my settings]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
13. User: ምን እንደቀየርኩ አሳይኝ [Show me what I changed]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
14. User: የእኔ ምርጫዎች ምንድናቸው? [What are my choices?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.
15. User: ፈጣን እየተጠቀምኩ ነው? [Am I using fast?]
   Bot should: Reply in Amharic — list the settings they set, one short line each; when nothing is set, say so and name the normal way.

## Setting two at once

1. User: ርካሹን መጀመሪያ ተጠቀም እና በሌሊት መልእክት አትላክልኝ [Use the cheapest first and don't message me at night]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
2. User: አስቀድመህ ጠይቀኝ እና ፈጣኑን ተጠቀም [Ask me first and use the fastest]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
3. User: ከ12 ሰዓት በላይ የሚወስድ አትጠቀም እና ሪፊል ያላቸውን ብቻ ተጠቀም [Never slower than 12 hours and refill only]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
4. User: ሊንኬ https://t.me/channelname/123 ነው እና እንደተለመደው 5000 እዘዝ [My link is https://t.me/channelname/123 and I usually order 5000]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
5. User: ርካሹን መጀመሪያ ተጠቀም እና አስቀድመህ ጠይቀኝ [Use the cheapest first and ask me first]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
6. User: በሌሊት መልእክት አትላክልኝ እና ሪፊል ያላቸውን ብቻ ተጠቀም [Don't message me at night and refill only]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
7. User: ሊንኬ https://t.me/channelname/123 ነው እና እንደተለመደው 500 እይታዎች እዘዝ [My link is https://t.me/channelname/123 and I usually order 500 views]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
8. User: ርካሹን ተጠቀም እና ከ6 ሰዓት በላይ የሚወስድ አትጠቀም [Use the cheapest and never slower than 6 hours]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
9. User: አስቀድመህ ጠይቀኝ እና በሌሊት መልእክት አትላክልኝ [Ask me first and don't message me at night]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.
10. User: ሊንኬ https://instagram.com/p/x ነው እና እንደተለመደው 10000 እዘዝ [My link is https://instagram.com/p/x and I usually order 10000]
   Bot should: Reply in Amharic — set both settings and confirm both in one short reply.

## Turning one off, clearing all

1. User: ርካሹን አቁም [Stop the cheapest]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
2. User: አስቀድመህ መጠየቅ አቁም [Stop asking first]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
3. User: የፍጥነት ገደቡን አቁም [Turn off the speed limit]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
4. User: የተቀመጠው ሊንኬን ሰርዝ [Delete my saved link]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
5. User: የጸጥታ ሰዓቱን ሰርዝ [Delete quiet hours]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
6. User: ቅንብሮቼን ሁሉ ሰርዝ [Clear all my settings]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
7. User: ቅንብሮቼን ዳግም አስጀምር [Reset my settings]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
8. User: የተለመደው ሊንኬን እርሳ [Forget my usual link]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
9. User: የድግግሞሽ መርሐግብሩን አቁም [Turn off the repeat schedule]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
10. User: የአገልግሎት እገዳዬን አቁም [Turn off my service ban]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
11. User: ፈጣን መጀመር አቁም [Turn off fast start]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
12. User: ድርብ ማረጋገጫ አቁም [Turn off double confirm]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
13. User: የሳምንቱን ገደብ ሰርዝ [Delete the weekly limit]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
14. User: የዋጋ ገደቡን አቁም [Turn off the price limit]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
15. User: ሪፊል ብቻ አቁም [Turn off refill only]
   Bot should: Reply in Amharic — turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.

## 4 — Fastest-first vs cheapest-first

1. User: ርካሹን መጀመሪያ ተጠቀም [Use the cheapest first]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
2. User: ሁልጊዜ ርካሹን ተጠቀም [Always use the cheapest]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
3. User: ርካሹን እመርጣለሁ [I prefer the cheapest]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
4. User: ከአሁን በኋላ ርካሹን መጀመሪያ ተጠቀም [From now on use the cheapest first]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
5. User: ፈጣኑን መጀመሪያ ተጠቀም [Use the fastest first]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
6. User: ሁልጊዜ ፈጣኑን ተጠቀም [Always use the fastest]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
7. User: ፈጣኑን እመርጣለሁ [I prefer the fastest]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
8. User: የyoutube likes ርካሹን ተጠቀም [Use the cheapest youtube likes]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
9. User: የtiktok followers ፈጣኑን ተጠቀም [Use the fastest tiktok followers]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
10. User: የዩቲዩብ ሰብስክራይበርዎች ርካሹን ተጠቀም [Use the cheapest youtube subscribers]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
11. User: የቴሌግራም አስተያየቶች ፈጣኑን ተጠቀም [Use the fastest telegram comments]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
12. User: ርካሹን ለፌስቡክ አባላት ተጠቀም [Use the cheapest for facebook members]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
13. User: ፈጣኑን ለዩቲዩብ ሰብስክራይበርዎች ተጠቀም [Use the fastest for youtube subscribers]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
14. User: ሁልጊዜ ርካሹን ለቲክቶክ ተጠቀም [Always use the cheapest for tiktok]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
15. User: የtiktok subscribers ርካሹን ተጠቀም [Use the cheapest tiktok subscribers]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
16. User: የinstagram likes ፈጣኑን ተጠቀም [Use the fastest instagram likes]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
17. User: የዩቲዩብ አባላት ርካሹን ተጠቀም [Use the cheapest youtube members]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
18. User: የዩቲዩብ አባላት ፈጣኑን ተጠቀም [Use the fastest youtube members]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
19. User: ርካሹን ለዩቲዩብ እይታዎች ተጠቀም [Use the cheapest for youtube views]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.
20. User: ፈጣኑን ለቲክቶክ ተከታዮች ተጠቀም [Use the fastest for tiktok followers]
   Bot should: Reply in Amharic — remember the pick order (cheapest or fastest first) and confirm it in one short line.

## 6 — Ask-first vs just do it

1. User: አገልግሎቱ ከተጣበቀ አስቀድመህ ጠይቀኝ [If the service gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
2. User: አገልግሎት ከመቀየርህ በፊት ጠይቀኝ [Ask me before you change service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
3. User: ሁልጊዜ አስቀድመህ ጠይቀኝ [Always ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
4. User: ሳትጠይቀኝ አታንቀሳቅስ [Don't move it without asking me]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
5. User: በራስህ አድርገው [Just do it yourself]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
6. User: መጠየቅ አያስፈልግም [No need to ask]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
7. User: አስቀድመህ መጠየቅ አቁም [Turn off ask first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
8. User: የፌስቡክ ሰብስክራይበርዎች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my facebook subscribers gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
9. User: አገልግሎት ከመቀየርህ በፊት ለዩቲዩብ እይታዎች ጠይቀኝ [Ask me before you change my youtube views service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
10. User: የኢንስታግራም ላይኮች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my instagram likes gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
11. User: አገልግሎት ከመቀየርህ በፊት ለቴሌግራም አባላት ጠይቀኝ [Ask me before you change my telegram members service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
12. User: የቴሌግራም እይታዎች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my telegram views gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
13. User: አገልግሎት ከመቀየርህ በፊት ለዩቲዩብ አስተያየቶች ጠይቀኝ [Ask me before you change my youtube comments service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
14. User: የፌስቡክ አስተያየቶች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my facebook comments gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
15. User: አገልግሎት ከመቀየርህ በፊት ለኢንስታግራም አስተያየቶች ጠይቀኝ [Ask me before you change my instagram comments service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
16. User: የቴሌግራም ተከታዮች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my telegram followers gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
17. User: አገልግሎት ከመቀየርህ በፊት ለፌስቡክ አስተያየቶች ጠይቀኝ [Ask me before you change my facebook comments service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
18. User: የዩቲዩብ ሰብስክራይበርዎች ከተጣበቀ አስቀድመህ ጠይቀኝ [If my youtube subscribers gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
19. User: አገልግሎት ከመቀየርህ በፊት ለዩቲዩብ ሰብስክራይበርዎች ጠይቀኝ [Ask me before you change my youtube subscribers service]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.
20. User: የዩቲዩብ አባላት ከተጣበቀ አስቀድመህ ጠይቀኝ [If my youtube members gets stuck ask me first]
   Bot should: Reply in Amharic — remember whether to ask first or just move a stuck order, and confirm it in one short line.

## 8 — Max slowness

1. User: ከ3 ሰዓት በላይ የሚወስድ አገልግሎት አትጠቀም [Don't use a service that takes more than 3 hours]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
2. User: ፈጣን አገልግሎቶችን ብቻ ተጠቀም [Only use fast services]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
3. User: ዝግ ያለ አገልግሎት አትጠቀም [Don't use a slow service]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
4. User: ፍጥነት አያስፈልገኝም [Speed doesn't matter to me]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
5. User: የፍጥነት ገደብ የለኝም [I have no speed limit]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
6. User: ከ6 ሰዓት በላይ ለቲክቶክ ተከታዮች አትጠቀም [Don't use a service slower than 6 hours for tiktok followers]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
7. User: ለኢንስታግራም ተከታዮች ፈጣን ብቻ ተጠቀም [Only use fast ones for instagram followers]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
8. User: ከ6 ሰዓት በላይ የሚወስድ አገልግሎት አትጠቀም [Don't use a service that takes more than 6 hours]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
9. User: ከ2 ሰዓት በላይ ለፌስቡክ ሰብስክራይበርዎች አትጠቀም [Don't use a service slower than 2 hours for facebook subscribers]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
10. User: ለቴሌግራም ላይኮች ፈጣን ብቻ ተጠቀም [Only use fast ones for telegram likes]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
11. User: ከ12 ሰዓት በላይ የሚወስድ አገልግሎት አትጠቀም [Don't use a service that takes more than 12 hours]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
12. User: ከ6 ሰዓት በላይ ለቲክቶክ አባላት አትጠቀም [Don't use a service slower than 6 hours for tiktok members]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
13. User: ከ2 ሰዓት በላይ የሚወስድ አገልግሎት አትጠቀም [Don't use a service that takes more than 2 hours]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
14. User: ከ12 ሰዓት በላይ ለቲክቶክ እይታዎች አትጠቀም [Don't use a service slower than 12 hours for tiktok views]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.
15. User: ለዩቲዩብ ተከታዮች ፈጣን ብቻ ተጠቀም [Only use fast ones for youtube followers]
   Bot should: Reply in Amharic — remember the slowest service allowed (or clear the limit) and confirm it in one short line.

## 11 — Default link

1. User: ሊንኬ https://tiktok.com/@x/video/1 ነው [My link is https://tiktok.com/@x/video/1]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
2. User: ሊንኬን አስታውስ https://instagram.com/p/x [Remember my link https://instagram.com/p/x]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
3. User: የእኔ የተለመደው ሊንክ https://t.me/channelname/123 ነው [My usual link is https://t.me/channelname/123]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
4. User: ሊንኬን እርሳ [Forget my link]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
5. User: ይህን ሊንክ አስታውስ https://t.me/channelname/123 [Remember this link https://t.me/channelname/123]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
6. User: ሊንኬን ወደ https://tiktok.com/@x/video/1 ቀይር [Change my link to https://tiktok.com/@x/video/1]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
7. User: ሊንኬ https://instagram.com/p/x ነው ሁልጊዜ ተጠቀምበት [My link is https://instagram.com/p/x, always use it]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
8. User: ነባሪ ሊንኬ https://t.me/channelname/123 አድርግ [Make https://t.me/channelname/123 my default link]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
9. User: ሊንኬ https://t.me/channelname/123 ነው [My link is https://t.me/channelname/123]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
10. User: የእኔ የተለመደው ሊንክ https://tiktok.com/@x/video/1 ነው [My usual link is https://tiktok.com/@x/video/1]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
11. User: ሊንኬን ወደ https://t.me/channelname/123 ቀይር [Change my link to https://t.me/channelname/123]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
12. User: ሊንኬን አስታውስ https://t.me/channelname/123 [Remember my link https://t.me/channelname/123]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
13. User: ይህን ሊንክ አስታውስ https://instagram.com/p/x [Remember this link https://instagram.com/p/x]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
14. User: ይህን ሊንክ አስታውስ https://tiktok.com/@x/video/1 [Remember this link https://tiktok.com/@x/video/1]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
15. User: ሊንኬን ወደ https://instagram.com/p/x ቀይር [Change my link to https://instagram.com/p/x]
   Bot should: Reply in Amharic — remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.

## 12 — Default quantity

1. User: እንደተለመደው 500 ቴሌግራም ተከታዮች እዘዝ [I usually order 500 telegram followers]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
2. User: የእኔ የተለመደው መጠን 2000 ነው [My usual quantity is 2000]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
3. User: እንደተለመደው 1000 ተከታዮች እፈልጋለሁ [I usually want 1000 followers]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
4. User: የተለመደው መጠኔን እርሳ [Forget my usual quantity]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
5. User: እንደተለመደው 10000 ቲክቶክ አባላት እዘዝ [I usually order 10000 tiktok members]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
6. User: የእኔ የተለመደው መጠን 1000 ነው [My usual quantity is 1000]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
7. User: እንደተለመደው 5000 ሰብስክራይበርዎች እፈልጋለሁ [I usually want 5000 subscribers]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
8. User: እንደተለመደው 5000 ቲክቶክ ሰብስክራይበርዎች እዘዝ [I usually order 5000 tiktok subscribers]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
9. User: እንደተለመደው 2000 ላይኮች እፈልጋለሁ [I usually want 2000 likes]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
10. User: እንደተለመደው 500 ዩቲዩብ አባላት እዘዝ [I usually order 500 youtube members]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
11. User: የእኔ የተለመደው መጠን 500 ነው [My usual quantity is 500]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
12. User: እንደተለመደው 500 እይታዎች እፈልጋለሁ [I usually want 500 views]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
13. User: እንደተለመደው 10000 ዩቲዩብ እይታዎች እዘዝ [I usually order 10000 youtube views]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
14. User: እንደተለመደው 1000 አስተያየቶች እፈልጋለሁ [I usually want 1000 comments]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
15. User: እንደተለመደው 2000 ቴሌግራም ሰብስክራይበርዎች እዘዝ [I usually order 2000 telegram subscribers]
   Bot should: Reply in Amharic — remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.

## 13 — Price ceiling per 1,000

1. User: ከ1000 በላይ 20 ብር አትክፈል [Don't pay more than 20 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
2. User: ከ1000 2 ብር በላይ አትክፈል [Never pay more than 2 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
3. User: ዋጋ አያስፈልገኝም [Price doesn't matter]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
4. User: የዋጋ ገደብ የለኝም [I have no price limit]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
5. User: ከ1000 20 ብር በላይ ለፌስቡክ ሰብስክራይበርዎች አትክፈል [Never pay more than 20 birr per 1000 for facebook subscribers]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
6. User: ከ1000 በላይ 10 ብር አትክፈል [Don't pay more than 10 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
7. User: ከ1000 20 ብር በላይ ለኢንስታግራም ተከታዮች አትክፈል [Never pay more than 20 birr per 1000 for instagram followers]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
8. User: ከ1000 በላይ 2 ብር አትክፈል [Don't pay more than 2 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
9. User: ከ1000 5 ብር በላይ አትክፈል [Never pay more than 5 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
10. User: ከ1000 10 ብር በላይ ለኢንስታግራም ሰብስክራይበርዎች አትክፈል [Never pay more than 10 birr per 1000 for instagram subscribers]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
11. User: ከ1000 100 ብር በላይ አትክፈል [Never pay more than 100 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
12. User: ከ1000 20 ብር በላይ ለቲክቶክ አባላት አትክፈል [Never pay more than 20 birr per 1000 for tiktok members]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
13. User: ከ1000 በላይ 100 ብር አትክፈል [Don't pay more than 100 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
14. User: ከ1000 50 ብር በላይ አትክፈል [Never pay more than 50 birr per 1000]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
15. User: ከ1000 20 ብር በላይ ለኢንስታግራም ላይኮች አትክፈል [Never pay more than 20 birr per 1000 for instagram likes]
   Bot should: Reply in Amharic — remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.

## 14 — Refill-only

1. User: ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
2. User: ሪፊል ብቻ [Refill only]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
3. User: ሪፊል አያስፈልገኝም [Refill doesn't matter]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
4. User: ለፌስቡክ እይታዎች ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for facebook views]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
5. User: ሪፊል ያላቸውን ፌስቡክ ላይኮች ብቻ ተጠቀም [Only use facebook likes with refill]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
6. User: ለፌስቡክ አባላት ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for facebook members]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
7. User: ሪፊል ያላቸውን ኢንስታግራም እይታዎች ብቻ ተጠቀም [Only use instagram views with refill]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
8. User: ለፌስቡክ ላይኮች ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for facebook likes]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
9. User: ሪፊል ያላቸውን ኢንስታግራም ሰብስክራይበርዎች ብቻ ተጠቀም [Only use instagram subscribers with refill]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
10. User: ለኢንስታግራም እይታዎች ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for instagram views]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
11. User: ሪፊል ያላቸውን ቴሌግራም እይታዎች ብቻ ተጠቀም [Only use telegram views with refill]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
12. User: ለፌስቡክ ሰብስክራይበርዎች ሪፊል ያላቸውን ብቻ ተጠቀም [Only use ones with refill for facebook subscribers]
   Bot should: Reply in Amharic — remember refill-only (or turn it off) and confirm it; only pick services that offer refill.

## 15 — Drip-feed

1. User: 1000 ተከታዮች በ2 ቀን አሰራጭ [Spread 1000 followers over 2 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
2. User: በዝግታ በ2 ቀን አድርስ [Deliver it slowly over 2 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
3. User: ድሪፕ ፊድ አድርግ [Drip-feed it]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
4. User: በተለመደው መንገድ አስገባ [Place it normally]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
5. User: 2000 ተከታዮች በ7 ቀን አሰራጭ [Spread 2000 followers over 7 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
6. User: በዝግታ በ3 ቀን አድርስ [Deliver it slowly over 3 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
7. User: 2000 እይታዎች በ3 ቀን አሰራጭ [Spread 2000 views over 3 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
8. User: 500 አስተያየቶች በ3 ቀን አሰራጭ [Spread 500 comments over 3 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
9. User: በዝግታ በ7 ቀን አድርስ [Deliver it slowly over 7 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
10. User: 500 ተከታዮች በ3 ቀን አሰራጭ [Spread 500 followers over 3 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
11. User: 10000 አስተያየቶች በ2 ቀን አሰራጭ [Spread 10000 comments over 2 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
12. User: 500 እይታዎች በ7 ቀን አሰራጭ [Spread 500 views over 7 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
13. User: 2000 ተከታዮች በ3 ቀን አሰራጭ [Spread 2000 followers over 3 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
14. User: በዝግታ በ1 ቀን አድርስ [Deliver it slowly over 1 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.
15. User: 10000 ተከታዮች በ2 ቀን አሰራጭ [Spread 10000 followers over 2 days]
   Bot should: Reply in Amharic — spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it.

## 16 — Auto-repeat

1. User: የፌስቡክ እይታዎችዬን በየሐሙስ ድገም [Repeat my facebook views every thursday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
2. User: በየቀኑ ድገም [Repeat it every day]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
3. User: በየሳምንቱ ድገም [Repeat it every week]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
4. User: ድግግሞሹን አቁም [Stop the repeat]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
5. User: ትዕዛዞቼን መድገም አቁም [Stop repeating my orders]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
6. User: የቲክቶክ ተከታዮችዬን በየማክሰኞ ድገም [Repeat my tiktok followers every tuesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
7. User: የቴሌግራም አባላትዬን በየረቡዕ ድገም [Repeat my telegram members every wednesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
8. User: የቲክቶክ አባላትዬን በየሐሙስ ድገም [Repeat my tiktok members every thursday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
9. User: የፌስቡክ እይታዎችዬን በየዓርብ ድገም [Repeat my facebook views every friday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
10. User: የፌስቡክ አባላትዬን በየማክሰኞ ድገም [Repeat my facebook members every tuesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
11. User: የቴሌግራም አስተያየቶችዬን በየማክሰኞ ድገም [Repeat my telegram comments every tuesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
12. User: የዩቲዩብ አስተያየቶችዬን በየሐሙስ ድገም [Repeat my youtube comments every thursday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
13. User: የቴሌግራም እይታዎችዬን በየሐሙስ ድገም [Repeat my telegram views every thursday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
14. User: የኢንስታግራም አባላትዬን በየማክሰኞ ድገም [Repeat my instagram members every tuesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
15. User: የዩቲዩብ አባላትዬን በየረቡዕ ድገም [Repeat my youtube members every wednesday]
   Bot should: Reply in Amharic — remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.

## 17 — Top up the missing part

1. User: የቀረውን ክፍል እራስህ አዝዝ [Order the missing part yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
2. User: ሁልጊዜ የቀረውን ጨምር [Always top up the missing part]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
3. User: ገንዘቡን ብቻ መልስ [Just refund the money]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
4. User: መጨመር አያስፈልግም [No need to top up]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
5. User: የቀረውን ላይኮች እራስህ አዝዝ [Order the missing likes yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
6. User: የፌስቡክ አስተያየቶች የቀረውን ጨምር [Top up the missing facebook comments]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
7. User: የቀረውን ተከታዮች እራስህ አዝዝ [Order the missing followers yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
8. User: የቲክቶክ አባላት የቀረውን ጨምር [Top up the missing tiktok members]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
9. User: የቀረውን አስተያየቶች እራስህ አዝዝ [Order the missing comments yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
10. User: የቲክቶክ ሰብስክራይበርዎች የቀረውን ጨምር [Top up the missing tiktok subscribers]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
11. User: የቀረውን አባላት እራስህ አዝዝ [Order the missing members yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
12. User: የፌስቡክ ሰብስክራይበርዎች የቀረውን ጨምር [Top up the missing facebook subscribers]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
13. User: የቀረውን እይታዎች እራስህ አዝዝ [Order the missing views yourself]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
14. User: የቴሌግራም ሰብስክራይበርዎች የቀረውን ጨምር [Top up the missing telegram subscribers]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.
15. User: የኢንስታግራም ሰብስክራይበርዎች የቀረውን ጨምር [Top up the missing instagram subscribers]
   Bot should: Reply in Amharic — remember to order the missing part instead of only refunding (or just refund) and confirm it.

## 18 — Place small orders without asking

1. User: ትንንሽ ትዕዛዞችን ሳትጠይቀኝ አስገባ [Place small orders without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
2. User: ከ100 ብር በታች ያሉ ትዕዛዞችን አስገባ [Place orders under 100 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
3. User: ትንንሽ ትዕዛዞችን ሳታረጋግጥ አስገባ [Place small orders without confirming]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
4. User: እንደገና እንድታረጋግጥ ጠይቀኝ [Ask me to confirm again]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
5. User: ሳትጠይቅ ማስገባት አቁም [Stop placing without asking]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
6. User: ከ50 ብር በታች ያሉ ፌስቡክ እይታዎች አስገባ [Place facebook views under 50 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
7. User: ትንንሽ ቴሌግራም እይታዎች ሳትጠይቀኝ አስገባ [Place small telegram views without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
8. User: ከ50 ብር በታች ሳታረጋግጥ አስገባ [Place under 50 birr without confirming]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
9. User: ከ100 ብር በታች ያሉ ቲክቶክ ሰብስክራይበርዎች አስገባ [Place tiktok subscribers under 100 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
10. User: ትንንሽ ዩቲዩብ አባላት ሳትጠይቀኝ አስገባ [Place small youtube members without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
11. User: ከ50 ብር በታች ያሉ ትዕዛዞችን አስገባ [Place orders under 50 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
12. User: ከ50 ብር በታች ያሉ ቴሌግራም አስተያየቶች አስገባ [Place telegram comments under 50 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
13. User: ትንንሽ ቲክቶክ እይታዎች ሳትጠይቀኝ አስገባ [Place small tiktok views without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
14. User: ከ100 ብር በታች ሳታረጋግጥ አስገባ [Place under 100 birr without confirming]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
15. User: ከ100 ብር በታች ያሉ ኢንስታግራም እይታዎች አስገባ [Place instagram views under 100 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
16. User: ከ50 ብር በታች ያሉ ቲክቶክ እይታዎች አስገባ [Place tiktok views under 50 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
17. User: ትንንሽ ፌስቡክ እይታዎች ሳትጠይቀኝ አስገባ [Place small facebook views without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
18. User: ከ100 ብር በታች ያሉ ቴሌግራም ላይኮች አስገባ [Place telegram likes under 100 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
19. User: ትንንሽ ፌስቡክ ሰብስክራይበርዎች ሳትጠይቀኝ አስገባ [Place small facebook subscribers without asking me]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.
20. User: ከ100 ብር በታች ያሉ ቲክቶክ አባላት አስገባ [Place tiktok members under 100 birr]
   Bot should: Reply in Amharic — remember the opt-in and the cap (at most 100 ETB) and confirm it back, naming the cap; bigger orders still get a Confirm card.

## 19 — Quiet hours

1. User: በሌሊት መልእክት አትላክልኝ [Don't message me at night]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
2. User: በሌሊት ምንም አትላክልኝ [Send nothing at night]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
3. User: ከምሽቱ 10 ሰዓት እስከ ጠዋት 7 ሰዓት መልእክት አትላክልኝ [Don't message me from 10pm to 7am]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
4. User: ጠዋት ብቻ መልእክት ላክልኝ [Message me only in the morning]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
5. User: የጸጥታ ሰዓቱን አቁም [Turn off quiet hours]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
6. User: በማንኛውም ጊዜ መልእክት ላክልኝ [Message me anytime]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
7. User: ከምሽቱ 11 ሰዓት ጀምሮ መልእክት አትላክልኝ [Don't message me from 11pm]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
8. User: እስከ ጠዋት 8 ሰዓት ድረስ መልእክት አትላክልኝ [Don't message me until 8am]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
9. User: ማታ መልእክት አትላክልኝ [Don't message me in the evening]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
10. User: ሌሊት ላይ አትላክልኝ [Don't send at night]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
11. User: ሌሊት ዝም በል [Be quiet at night]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
12. User: ከምሽቱ 9 ሰዓት ጀምሮ ዝም በል [Be quiet from 9pm]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
13. User: ጠዋት 7 ሰዓት ላይ መልእክት ላክልኝ [Send me messages at 7am]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
14. User: የሌሊት መልእክቶችን ጠዋት ላክልኝ [Send the night messages in the morning]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
15. User: ምሽት ላይ መልእክት አትላክልኝ [Don't message me in the evening]
   Bot should: Reply in Amharic — remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.

## 20 — Delivery deadline

1. User: እስከ ዓርብ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by Friday 5 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
2. User: እስከ ነገ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 5 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
3. User: በ3 ሰዓት ውስጥ ያስፈልገኛል [I need it within 3 hours]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
4. User: ያለ ገደቡ አስገባ [Place it without the deadline]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
5. User: ገደቡን እርሳ [Forget the deadline]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
6. User: እስከ ረቡዕ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by wednesday 5 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
7. User: እስከ ነገ 6 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 6 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
8. User: እስከ ነገ 1 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 1 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
9. User: በ2 ሰዓት ውስጥ ያስፈልገኛል [I need it within 2 hours]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
10. User: እስከ ሐሙስ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by thursday 5 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
11. User: እስከ ነገ 3 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 3 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
12. User: በ12 ሰዓት ውስጥ ያስፈልገኛል [I need it within 12 hours]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
13. User: እስከ ዓርብ 5 ሰዓት ድረስ ያስፈልገኛል [I need it by friday 5 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
14. User: እስከ ነገ 2 ሰዓት ድረስ ያስፈልገኛል [I need it by tomorrow 2 o'clock]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
15. User: በ1 ሰዓት ውስጥ ያስፈልገኛል [I need it within 1 hours]
   Bot should: Reply in Amharic — only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.

## 21 — Favourite services

1. User: የምወደው አገልግሎት 7000 ነው [My favourite service is 7000]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
2. User: አገልግሎት 6139ን ተወዳጅ አድርግ [Make service 6139 a favourite]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
3. User: ተወዳጆቼን መጀመሪያ ተጠቀም [Use my favourites first]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
4. User: ተወዳጆቼን እርሳ [Forget my favourites]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
5. User: የምወደው አገልግሎት 6001 ነው [My favourite service is 6001]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
6. User: አገልግሎት 5535ን ተወዳጅ አድርግ [Make service 5535 a favourite]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
7. User: የምወደው አገልግሎት 5535 ነው [My favourite service is 5535]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
8. User: አገልግሎት 7501ን ተወዳጅ አድርግ [Make service 7501 a favourite]
   Bot should: Reply in Amharic — remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.

## 24 — Low balance alert

1. User: ሚዛኔ ከ1000 ብር በታች ሲሆን ንገረኝ [Tell me when my balance is below 1000 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
2. User: ሚዛኔ ሲቀንስ ንገረኝ [Tell me when my balance drops]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
3. User: የሚዛን ማስጠንቅቂያ አቁም [Turn off the balance alert]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
4. User: ሚዛኔ ከ2000 ብር በታች ከሆነ አሳውቀኝ [Alert me when my balance is below 2000 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
5. User: ሚዛኔ ከ2000 ብር በታች ሲሆን ንገረኝ [Tell me when my balance is below 2000 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
6. User: ሚዛኔ ከ1000 ብር በታች ከሆነ አሳውቀኝ [Alert me when my balance is below 1000 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
7. User: ሚዛኔ ከ500 ብር በታች ሲሆን ንገረኝ [Tell me when my balance is below 500 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
8. User: ሚዛኔ ከ100 ብር በታች ከሆነ አሳውቀኝ [Alert me when my balance is below 100 birr]
   Bot should: Reply in Amharic — remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.

## 25 — Weekly spending limit

1. User: በሳምንት ከ1000 ብር በላይ አታውጣ [Don't spend more than 1000 birr a week]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
2. User: የሳምንቱ ወጪ ገደብ 500 ነው [My weekly spending limit is 500]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
3. User: የሳምንቱን ገደብ አቁም [Turn off the weekly limit]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
4. User: የሳምንቱ ወጪ ገደብ 2000 ነው [My weekly spending limit is 2000]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
5. User: በሳምንት ከ500 ብር በላይ አታውጣ [Don't spend more than 500 birr a week]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
6. User: በሳምንት ከ100 ብር በላይ አታውጣ [Don't spend more than 100 birr a week]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
7. User: በሳምንት ከ2000 ብር በላይ አታውጣ [Don't spend more than 2000 birr a week]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.
8. User: የሳምንቱ ወጪ ገደብ 100 ነው [My weekly spending limit is 100]
   Bot should: Reply in Amharic — remember the weekly spending limit (or turn it off) and confirm it.

## 26 — One-tap usual order

1. User: እንደተለመደው እዘዝ [Order as usual]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
2. User: የተለመደውን ስጠኝ [Give me the usual]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
3. User: እንደተለመደው አስገባ [Place it as usual]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
4. User: የተለመደውን ቲክቶክ አስተያየቶች እዘዝ [Order my usual tiktok comments]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
5. User: እንደተለመደው 1000 አስተያየቶች እዘዝ [Order 1000 comments as usual]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
6. User: የተለመደውን ቲክቶክ አባላት እዘዝ [Order my usual tiktok members]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
7. User: እንደተለመደው 2000 ሰብስክራይበርዎች እዘዝ [Order 2000 subscribers as usual]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.
8. User: የተለመደውን ኢንስታግራም ላይኮች እዘዝ [Order my usual instagram likes]
   Bot should: Reply in Amharic — reuse the last order's service, link and quantity and show the Confirm card.

## 27 — Pause my repeats

1. User: የሚደገሙ ትዕዛዞቼን አቁም [Pause my repeating orders]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
2. User: ድግግሞሹን አቁም [Pause the repeat]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
3. User: የሚደገሙትን እንደገና ጀምር [Resume my repeats]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
4. User: የፌስቡክ ሰብስክራይበርዎች ድግግሞሽ አቁም [Pause the facebook subscribers repeat]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
5. User: ድግግሞሹን ለቲክቶክ አስተያየቶች አቁም [Pause the repeat for tiktok comments]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
6. User: የዩቲዩብ እይታዎች ድግግሞሽ አቁም [Pause the youtube views repeat]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
7. User: ድግግሞሹን ለዩቲዩብ ላይኮች አቁም [Pause the repeat for youtube likes]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.
8. User: የፌስቡክ አስተያየቶች ድግግሞሽ አቁም [Pause the facebook comments repeat]
   Bot should: Reply in Amharic — pause every repeating order (or resume them) and confirm how many were paused.

## 30 — Watch my post and top up

1. User: ፖስቴን ተከታትለህ ጨምር [Watch my post and add more]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
2. User: ፖስቴን ተከታተል [Watch my post]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
3. User: ፖስቴን መከታተል አቁም [Stop watching my post]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
4. User: የቴሌግራም ፖስቴን ተከታተል [Watch my telegram post]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
5. User: ፖስቴን ተከታትለህ ሰብስክራይበርዎች ጨምር [Watch my post and add subscribers]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
6. User: የኢንስታግራም ፖስቴን ተከታተል [Watch my instagram post]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
7. User: ፖስቴን ተከታትለህ እይታዎች ጨምር [Watch my post and add views]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.
8. User: የቲክቶክ ፖስቴን ተከታተል [Watch my tiktok post]
   Bot should: Reply in Amharic — remember the watch request and say plainly it isn't switched on yet.

## 31 — Saved links list

1. User: ይህን ሊንክ እንደ ፌስቡክ ሊንኬ አስቀምጥ https://instagram.com/p/x [Save this link as my facebook link]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
2. User: የቲክቶክ ሊንኬን ተጠቀም [Use my tiktok link]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
3. User: የተቀመጡ ሊንኮቼን እርሳ [Forget my saved links]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
4. User: ይህን ሊንክ እንደ ቴሌግራም ሊንኬ አስቀምጥ https://instagram.com/p/x [Save this link as my telegram link]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
5. User: የዩቲዩብ ሊንኬን ተጠቀም [Use my youtube link]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
6. User: ይህን ሊንክ እንደ ቴሌግራም ሊንኬ አስቀምጥ https://tiktok.com/@x/video/1 [Save this link as my telegram link]
   Bot should: Reply in Amharic — remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.

## 32 — Best time to deliver

1. User: አባላት ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order members?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.
2. User: ፈጣን ለማድረስ መቼ ማዘዝ አለብኝ? [When should I order for fastest delivery?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.
3. User: እይታዎች ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order views?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.
4. User: ሰብስክራይበርዎች ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order subscribers?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.
5. User: ላይኮች ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order likes?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.
6. User: ተከታዮች ለማዘዝ የተሻለው ጊዜ መቼ ነው? [When is the best time to order followers?]
   Bot should: Reply in Amharic — answer with the fastest service's start time for what they asked.

## 33 — Wait for a lower price

1. User: ዋጋው እስከ 5 ብር እስኪወርድ ጠብቅ [Wait until the price drops to 5 birr]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.
2. User: ዋጋው ሲቀንስ ንገረኝ [Tell me when the price drops]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.
3. User: መጠበቅ አቁም [Stop waiting]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.
4. User: ዋጋው እስከ 20 ብር እስኪወርድ ጠብቅ [Wait until the price drops to 20 birr]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.
5. User: ዋጋው እስከ 2 ብር እስኪወርድ ጠብቅ [Wait until the price drops to 2 birr]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.
6. User: ዋጋው እስከ 50 ብር እስኪወርድ ጠብቅ [Wait until the price drops to 50 birr]
   Bot should: Reply in Amharic — remember the price to wait for and say plainly the price watch isn't switched on yet.

## 34 — Auto-cancel if too slow

1. User: ከ2 ሰዓት በላይ ከወሰደ ሰርዝ [Cancel it if it takes more than 2 hours]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.
2. User: ዝግ ከሆነ በራስ-ሰርዝ [Auto-cancel if it is slow]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.
3. User: ራስ-ሰርዝ አቁም [Turn off auto-cancel]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.
4. User: ከ12 ሰዓት በላይ ከወሰደ ሰርዝ [Cancel it if it takes more than 12 hours]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.
5. User: ከ1 ሰዓት በላይ ከወሰደ ሰርዝ [Cancel it if it takes more than 1 hours]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.
6. User: ከ3 ሰዓት በላይ ከወሰደ ሰርዝ [Cancel it if it takes more than 3 hours]
   Bot should: Reply in Amharic — remember the auto-cancel time (or turn it off) and confirm it.

## 35 — Monthly report

1. User: የወር ሪፖርት ላክልኝ [Send me a monthly report]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.
2. User: የወር ወጪ ሪፖርት [Monthly spending report]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.
3. User: የወር ሪፖርቱን አቁም [Stop the monthly report]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.
4. User: የወር ሪፖርት እፈልጋለሁ [I want a monthly report]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.
5. User: የወር ሪፖርት ላክልኝ እባክህ [Please send me a monthly report]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.
6. User: የወር ማጠቃለያ ላክልኝ [Send me a monthly summary]
   Bot should: Reply in Amharic — remember the monthly report (or stop it) and say plainly it isn't switched on yet.

## 36 — Start fast only

1. User: ፈጣን የሚጀምሩትን ብቻ ተጠቀም [Only use ones that start fast]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.
2. User: ፈጣን መጀመር ብቻ [Fast start only]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.
3. User: ፈጣን መጀመር አቁም [Turn off fast start only]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.
4. User: ፈጣን የሚጀምር ቲክቶክ አባላት ብቻ ተጠቀም [Only use fast-starting tiktok members]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.
5. User: ፈጣን መጀመር ለፌስቡክ እይታዎች [Fast start for facebook views]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.
6. User: ፈጣን የሚጀምር ቲክቶክ ሰብስክራይበርዎች ብቻ ተጠቀም [Only use fast-starting tiktok subscribers]
   Bot should: Reply in Amharic — remember start-fast-only (or turn it off) and confirm it.

## 37 — Language lock

1. User: ሁልጊዜ በአማርኛ መልስ [Always reply in Amharic]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.
2. User: በአማርኛ ብቻ ንገረኝ [Tell me in Amharic only]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.
3. User: በእንግሊዝኛ ብቻ መልስ [Reply in English only]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.
4. User: የቋንቋ መቆለፊያውን አቁም [Turn off the language lock]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.
5. User: ሁልጊዜ በእንግሊዝኛ መልስ [Always reply in English]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.
6. User: በአማርኛ ብቻ መልስ [Reply in Amharic only]
   Bot should: Reply in Amharic — remember the locked reply language (or unlock it) and confirm it; always reply in that language.

## 38 — Double confirm for big orders

1. User: ለትላልቅ ትዕዛዞች ሁለት ጊዜ ጠይቀኝ [Ask me twice for big orders]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.
2. User: ከ100 ብር በላይ ሁለት ጊዜ አረጋግጥ [Double-confirm over 100 birr]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.
3. User: ድርብ ማረጋገጫውን አቁም [Turn off double confirm]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.
4. User: ትልልቅ ትዕዛዞችን ሁለት ጊዜ አረጋግጥ [Double-confirm big orders]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.
5. User: ከ500 ብር በላይ ሁለት ጊዜ አረጋግጥ [Double-confirm over 500 birr]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.
6. User: ከ2000 ብር በላይ ሁለት ጊዜ አረጋግጥ [Double-confirm over 2000 birr]
   Bot should: Reply in Amharic — remember the double-confirm level (or turn it off) and confirm it.

## 39 — Never use these services

1. User: አገልግሎት 7000ን በጭራሽ አትጠቀም [Never use service 7000]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.
2. User: አገልግሎት 6001ን አትጠቀም [Don't use service 6001]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.
3. User: አገልግሎት 5535ን አስወግድ [Remove service 5535]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.
4. User: አገልግሎት 5535ን በጭራሽ አትጠቀም [Never use service 5535]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.
5. User: አገልግሎት 5535ን አትጠቀም [Don't use service 5535]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.
6. User: አገልግሎት 6139ን አስወግድ [Remove service 6139]
   Bot should: Reply in Amharic — remember the banned service(s) and confirm it; never pick them.

## 40 — Try new services

1. User: አዳዲስ አገልግሎቶችን ሞክር [Try new services]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.
2. User: አዳዲሶቹን እፈልጋለሁ [I want the new ones]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.
3. User: አዳዲስ አገልግሎቶችን አትጠቀም [Don't use new services]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.
4. User: አዳዲስ ቲክቶክ አስተያየቶች ሞክር [Try new tiktok comments]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.
5. User: አዳዲሶቹን ሞክር [Try the new ones]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.
6. User: አዳዲስ ቴሌግራም ሰብስክራይበርዎች ሞክር [Try new telegram subscribers]
   Bot should: Reply in Amharic — remember try-new-services (or turn it off) and confirm it.

## 1 — Split test on/off (NOT approved)

1. User: የሙከራ ትዕዛዝ አታድርግ [Don't do a test order]
   Bot should: Reply in Amharic — say the test order is how big orders are placed; it cannot be turned off.
2. User: ሙከራውን አቁም [Stop the test]
   Bot should: Reply in Amharic — say the test order is how big orders are placed; it cannot be turned off.

## 2 — Test size (NOT approved)

1. User: ሙከራውን 20% አድርግ [Make the test 20%]
   Bot should: Reply in Amharic — say the test is always 10% of the order.
2. User: ሙከራውን አሳድግ [Make the test bigger]
   Bot should: Reply in Amharic — say the test is always 10% of the order.

## 3 — The 400 ETB line (NOT approved)

1. User: የሙከራ መስመሩን 1000 ብር አድርግ [Make the test line 1000 birr]
   Bot should: Reply in Amharic — say orders over 400 ETB get a test order; the line cannot be changed.
2. User: የሙከራ መስመሩን ቀይር [Change the test line]
   Bot should: Reply in Amharic — say orders over 400 ETB get a test order; the line cannot be changed.

## 5 — How much extra is allowed (NOT approved)

1. User: 20% ተጨማሪ ፍቀድ [Allow 20% extra]
   Bot should: Reply in Amharic — say the extra Paxyo covers is at most 10% of the confirmed total.
2. User: ተጨማሪ ወጪ ፍቀድ [Allow extra spending]
   Bot should: Reply in Amharic — say the extra Paxyo covers is at most 10% of the confirmed total.

## 7 — How many tries (NOT approved)

1. User: 10 ጊዜ ሞክር [Try 10 times]
   Bot should: Reply in Amharic — say the bot tries up to 5 services, then refunds.
2. User: ሁለት ጊዜ ብቻ ሞክር [Try only twice]
   Bot should: Reply in Amharic — say the bot tries up to 5 services, then refunds.

## 9 — PIN ONE SERVICE (NOT approved)

1. User: አገልግሎት 6139ን ቋሚ አድርግ [Pin service 6139]
   Bot should: Reply in Amharic — say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.
2. User: አገልግሎት 7501ን ብቻ ተጠቀም [Use only service 7501]
   Bot should: Reply in Amharic — say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.

## 10 — SPENDING CAP (NOT approved)

1. User: በአንድ ትዕዛዝ ከ1000 ብር በላይ አታውጣ [Never spend more than 1000 birr on one order]
   Bot should: Reply in Amharic — say an order never costs more than the confirmed total; there is no separate spending cap.
2. User: የወጪ ገደብ 100 [Spending cap 100]
   Bot should: Reply in Amharic — say an order never costs more than the confirmed total; there is no separate spending cap.

## 22 — Split across services (NOT approved)

1. User: ትዕዛዜን በአገልግሎቶች መካከል ከፍል [Split my order between services]
   Bot should: Reply in Amharic — say one order goes on one service; it cannot be split across services.
2. User: ሁለት አገልግሎቶችን ተጠቀም [Use two services]
   Bot should: Reply in Amharic — say one order goes on one service; it cannot be split across services.

## 23 — Delivery report (NOT approved)

1. User: ከእያንዳንዱ ማድረስ በኋላ ሪፖርት ላክልኝ [Send me a report after each delivery]
   Bot should: Reply in Amharic — say the bot already tells them when an order is delivered.
2. User: የማድረስ ሪፖርት እፈልጋለሁ [I want a delivery report]
   Bot should: Reply in Amharic — say the bot already tells them when an order is delivered.

## 28 — Price alert for my usual service (NOT approved)

1. User: የተለመደው አገልግሎቴ ዋጋ ሲቀንስ ንገረኝ [Tell me when my usual service gets cheaper]
   Bot should: Reply in Amharic — say the bot cannot watch the price of one service yet.
2. User: የተለመደው ዋጋ ሲቀንስ ንገረኝ [Tell me when my usual price drops]
   Bot should: Reply in Amharic — say the bot cannot watch the price of one service yet.

## 29 — All or nothing (NOT approved)

1. User: ሁሉም ወይም ምንም [All or nothing]
   Bot should: Reply in Amharic — say a short delivery is refunded for the missing part; all-or-nothing is not offered.
2. User: በחלקው አታድርስ [Don't deliver partially]
   Bot should: Reply in Amharic — say a short delivery is refunded for the missing part; all-or-nothing is not offered.
