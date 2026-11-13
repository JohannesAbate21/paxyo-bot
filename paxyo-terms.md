# Paxyo Terms & Conditions

Source: https://paxyo.et/home.php (fetched 2026-11-13)

1. Introduction
Welcome to Paxyo. By accessing or using our services, you agree to be bound by these Terms & Conditions. These terms apply to all users of the platform. If you do not agree with any part of these terms, you should not use Paxyo.

2. Description of Services
Paxyo provides digital marketing and social media engagement services, including likes, views, followers, and other engagement metrics.

Paxyo operates as a licensed marketing service provider in Ethiopia and is not affiliated with any social media platforms.

3. User Responsibilities
Users agree to:
- Provide accurate and valid order details (links, usernames, etc.)
- Ensure accounts or content are public and accessible
- Not use Paxyo for illegal, harmful, or misleading purposes

Paxyo is not responsible for issues caused by incorrect information provided by the user.

4. Orders & Processing
- Orders begin after payment is successfully completed.
- Orders cannot be canceled or modified once processing has started.
- Delivery time may vary depending on the service and demand.
- Some services may start instantly, while others may take time.

5. Service Performance Disclaimer
- Paxyo does not guarantee permanent results for all services.
- Social media platforms may update their systems, which can affect delivery.
- Drops in followers, likes, or views may occur over time.

6. Refund & Balance Policy
- Paxyo does not provide refunds to bank accounts, mobile money, or external payment methods.
- If an order is partially completed, canceled, or fails, the remaining amount will be returned to the user's Paxyo balance.
- Users can reuse this balance to place new orders at any time.
- Paxyo balance cannot be withdrawn as cash.

7. Data Privacy & Security
- Paxyo respects user privacy and does not sell, rent, or share user data with third parties.
- User information is stored using secure systems and modern encryption practices to protect against unauthorized access.
- Sensitive data is handled with strict internal controls and is only accessible when necessary for system operation or support.
- Paxyo team members do not access personal user data unless required to resolve a support issue.
- We continuously improve our security measures to keep user data safe.

8. Pricing & Payments
- All prices are displayed inside the platform and may change at any time.
- Users are responsible for reviewing service details before placing orders.
- Paxyo is not responsible for issues caused by third-party payment providers.

9. Account & Security
- Users are responsible for maintaining the security of their accounts.
- Paxyo is not liable for unauthorized access due to user negligence.

10. Prohibited Activities
Users must not:
- Use Paxyo for fraudulent or deceptive purposes
- Attempt to exploit or harm the system
- Use automation or bots to abuse services

Violations may result in account suspension.

11. Account Suspension & Termination
Paxyo reserves the right to suspend or terminate accounts that violate these terms or engage in suspicious activity.

No refunds will be provided in such cases.

12. Limitation of Liability
Paxyo is not responsible for:
- Any loss of profits, data, or business opportunities
- Social media account restrictions or bans
- Any indirect damages resulting from service use

All services are used at the user's own risk.

13. Service Availability
Paxyo aims to provide continuous service but does not guarantee uninterrupted operation. Temporary downtime may occur due to maintenance or technical issues.

14. Contact & Support
Paxyo is a licensed marketing company in Ethiopia. Users can contact us at any time through our official support channels.

15. Changes to Terms
Paxyo may update these Terms & Conditions at any time. Continued use of the platform means you accept any changes.

Last updated: March 2026

';

 var dark=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches;
 function show(title,html){
 if(!window.Swal){alert(title);return}
 Swal.fire({title:title,html:html,confirmButtonText:'Close',confirmButtonColor:'#3275dd',
 background:dark?'#141923':'#fff',color:dark?'#f1f5f9':'#0f172a',width:560});
 }
 document.addEventListener('click',function(e){
 var b=e.target.closest('[data-open]'); if(!b)return;
 if(b.dataset.open==='about') show('About Us',ABOUT); else show('Terms & Conditions
