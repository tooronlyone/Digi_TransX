import { useEffect } from 'react';

const mainPageHtml = "<!-- NAVBAR - Copied from transporter_dashboard.html style -->\n<nav class=\"navbar\" id=\"navbar\">\n    <div class=\"navbar-left\">\n        <div class=\"navbar-logo\">\n            <div class=\"logo-icon\">\n                <i class=\"fas fa-truck\"></i>\n            </div>\n            <a href=\"/\" class=\"navbar-brand\">Digi_TransX</a>\n        </div>\n        <img src=\"/src/assets/brand/logo-mark.svg\" alt=\"Transport Logo\" class=\"transport-logo\">\n    </div>\n    \n    <div class=\"navbar-right\">\n        <ul class=\"nav-links\">\n            <li><a href=\"#how-it-works\">How It Works</a></li>\n            <li><a href=\"#features\">Features</a></li>\n            <li><a href=\"#for-who\">For You</a></li>\n        </ul>\n        <a href=\"/login\" class=\"btn-ghost\">Login</a>\n        <a href=\"/signup\" class=\"btn-primary-nav\">Get Started</a>\n        <button class=\"hamburger\"><i class=\"fas fa-bars\"></i></button>\n    </div>\n</nav>\n\n<!-- HERO SECTION -->\n<section class=\"hero\">\n    <div class=\"hero-content\">\n        <div class=\"hero-badge\"><span class=\"dot\"></span> Now Live in Pakistan 🇵🇰</div>\n        <h1 class=\"hero-title\">\n            Pakistan's <span class=\"accent\">Smartest</span>\n            <span class=\"line-2\">Transport Platform</span>\n        </h1>\n        <p class=\"hero-subtitle\">Connect clients with trusted transporters. Place orders, track shipments in real time, manage your fleet, and grow your logistics business — all in one place.</p>\n        <div class=\"hero-cta\">\n            <a href=\"/signup?role=client\" class=\"btn-hero-primary\"><i class=\"fas fa-box\"></i> I Need Transport</a>\n            <a href=\"/signup?role=transporter\" class=\"btn-hero-secondary\"><i class=\"fas fa-truck\"></i> I'm a Transporter</a>\n        </div>\n    </div>\n\n    <!-- Floating Cards - Styled like dashboard cards -->\n    <div class=\"hero-visual\">\n        <div class=\"floating-card c1\">\n            <div class=\"card-row\">\n                <div class=\"cicon ci-orange\"><i class=\"fas fa-truck-moving\"></i></div>\n                <span class=\"sbadge sb-live\">● Live</span>\n            </div>\n            <div class=\"clabel\">Active Shipment</div>\n            <div class=\"cval\">DTX-2026-0142</div>\n            <div class=\"route-row\">\n                <span class=\"rdot\" style=\"background: var(--success)\"></span> Karachi\n                <div class=\"rline\"></div>\n                <span class=\"rdot\" style=\"background: var(--accent-primary)\"></span> Lahore\n            </div>\n            <div class=\"progress-bar\"><div class=\"progress-fill\"></div></div>\n        </div>\n        <div class=\"floating-card c2\">\n            <div class=\"card-row\">\n                <div class=\"cicon ci-green\"><i class=\"fas fa-wallet\"></i></div>\n                <span class=\"sbadge sb-blue\">This Month</span>\n            </div>\n            <div class=\"clabel\">Total Earnings</div>\n            <div class=\"cval\">Rs. 142,500 <small>+18%</small></div>\n        </div>\n        <div class=\"floating-card c3\">\n            <div class=\"card-row\">\n                <div class=\"cicon ci-blue\"><i class=\"fas fa-clipboard-list\"></i></div>\n                <span class=\"sbadge sb-pending\">Pending</span>\n            </div>\n            <div class=\"clabel\">New Job Request</div>\n            <div class=\"cval\" style=\"font-size:16px;margin-top:4px\">Islamabad → Faisalabad</div>\n            <div class=\"route-row\" style=\"margin-top:8px\">\n                <i class=\"fas fa-weight-hanging\" style=\"color:var(--text-muted)\"></i>\n                <span>12 Tons</span>\n                <span style=\"margin-left:auto;color:var(--accent-primary);font-weight:700\">Rs. 28,000</span>\n            </div>\n        </div>\n    </div>\n</section>\n\n<!-- STATS BAR - Dashboard style -->\n<div class=\"stats-bar\">\n    <div class=\"stats-grid\">\n        <div class=\"stat-item reveal\">\n            <div class=\"stat-number\"><span id=\"s1\">0</span><span class=\"acc\">+</span></div>\n            <div class=\"stat-label\">Active Transporters</div>\n        </div>\n        <div class=\"stat-item reveal\">\n            <div class=\"stat-number\"><span id=\"s2\">0</span><span class=\"acc\">+</span></div>\n            <div class=\"stat-label\">Orders Completed</div>\n        </div>\n        <div class=\"stat-item reveal\">\n            <div class=\"stat-number\"><span id=\"s3\">0</span></div>\n            <div class=\"stat-label\">Cities Covered</div>\n        </div>\n        <div class=\"stat-item reveal\">\n            <div class=\"stat-number\">Rs.<span id=\"s4\">0</span><span class=\"acc\">M+</span></div>\n            <div class=\"stat-label\">Paid to Transporters</div>\n        </div>\n    </div>\n</div>\n\n<!-- HOW IT WORKS SECTION -->\n<section class=\"section\" id=\"how-it-works\">\n    <span class=\"section-label reveal\">How It Works</span>\n    <h2 class=\"section-title reveal\">Simple. Fast. Reliable.</h2>\n    <p class=\"section-subtitle reveal\">Whether you're shipping goods or driving trucks, getting started takes less than 5 minutes.</p>\n    <div class=\"how-tabs reveal\">\n        <button class=\"how-tab active\" onclick=\"switchTab('client')\">For Clients</button>\n        <button class=\"how-tab\" onclick=\"switchTab('transporter')\">For Transporters</button>\n    </div>\n    <div class=\"steps-panel active\" id=\"panel-client\">\n        <div class=\"steps-grid\">\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">01</div>\n                <div class=\"step-icon\"><i class=\"fas fa-user-plus\"></i></div>\n                <div class=\"step-title\">Create Your Account</div>\n                <div class=\"step-desc\">Sign up in 2 minutes. Tell us what you ship, your city, and your business type.</div>\n            </div>\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">02</div>\n                <div class=\"step-icon\"><i class=\"fas fa-box\"></i></div>\n                <div class=\"step-title\">Post Your Order</div>\n                <div class=\"step-desc\">Enter pickup location, delivery destination, cargo type and weight. Get matched with verified transporters instantly.</div>\n            </div>\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">03</div>\n                <div class=\"step-icon\"><i class=\"fas fa-map-marked-alt\"></i></div>\n                <div class=\"step-title\">Track & Receive</div>\n                <div class=\"step-desc\">Follow your shipment live from pickup to delivery. Get notifications at every step.</div>\n            </div>\n        </div>\n    </div>\n    <div class=\"steps-panel\" id=\"panel-transporter\">\n        <div class=\"steps-grid\">\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">01</div>\n                <div class=\"step-icon\"><i class=\"fas fa-truck\"></i></div>\n                <div class=\"step-title\">Register Your Fleet</div>\n                <div class=\"step-desc\">Add your trucks with type, capacity, and documents. Get verified and go live on the platform.</div>\n            </div>\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">02</div>\n                <div class=\"step-icon\"><i class=\"fas fa-clipboard-check\"></i></div>\n                <div class=\"step-title\">Accept Jobs</div>\n                <div class=\"step-desc\">Browse available shipment orders near you. Accept jobs that match your fleet and route. No middlemen.</div>\n            </div>\n            <div class=\"step-card reveal\">\n                <div class=\"step-number\">03</div>\n                <div class=\"step-icon\"><i class=\"fas fa-wallet\"></i></div>\n                <div class=\"step-title\">Deliver & Earn</div>\n                <div class=\"step-desc\">Complete the delivery, update the status, and watch your earnings grow. Withdraw anytime to your bank account.</div>\n            </div>\n        </div>\n    </div>\n</section>\n\n<!-- FOR WHO SECTION -->\n<section class=\"section for-who\" id=\"for-who\">\n    <span class=\"section-label reveal\">Choose Your Path</span>\n    <h2 class=\"section-title reveal\">Built for Both Sides</h2>\n    <p class=\"section-subtitle reveal\">Digi_TransX serves both businesses that need to ship goods and transporters who want to grow their income.</p>\n    <div class=\"for-who-grid\">\n        <div class=\"for-card reveal\">\n            <div class=\"for-card-icon ci-blue2\"><i class=\"fas fa-building\"></i></div>\n            <h3 class=\"for-card-title\">For Clients</h3>\n            <p class=\"for-card-desc\">Businesses, factories, retailers — anyone who needs to move goods across Pakistan reliably and affordably.</p>\n            <ul class=\"feature-list\">\n                <li><span class=\"chk chk-blue\"><i class=\"fas fa-check\"></i></span> Post orders in under 2 minutes</li>\n                <li><span class=\"chk chk-blue\"><i class=\"fas fa-check\"></i></span> Verified, rated transporters only</li>\n                <li><span class=\"chk chk-blue\"><i class=\"fas fa-check\"></i></span> Real-time shipment tracking</li>\n                <li><span class=\"chk chk-blue\"><i class=\"fas fa-check\"></i></span> Digital invoices and payment history</li>\n                <li><span class=\"chk chk-blue\"><i class=\"fas fa-check\"></i></span> Cancel anytime before pickup</li>\n            </ul>\n            <a href=\"/signup?role=client\" class=\"btn-for btn-blue\"><i class=\"fas fa-box\"></i> Start Shipping Now</a>\n        </div>\n        <div class=\"for-card reveal\">\n            <div class=\"for-card-icon ci-orange2\"><i class=\"fas fa-truck\"></i></div>\n            <h3 class=\"for-card-title\">For Transporters</h3>\n            <p class=\"for-card-desc\">Fleet owners, individual truck owners — grow your business with a steady stream of verified shipment jobs.</p>\n            <ul class=\"feature-list\">\n                <li><span class=\"chk chk-orange\"><i class=\"fas fa-check\"></i></span> Manage your entire fleet in one place</li>\n                <li><span class=\"chk chk-orange\"><i class=\"fas fa-check\"></i></span> Browse & accept jobs instantly</li>\n                <li><span class=\"chk chk-orange\"><i class=\"fas fa-check\"></i></span> Track earnings and wallet balance</li>\n                <li><span class=\"chk chk-orange\"><i class=\"fas fa-check\"></i></span> Build your rating and reputation</li>\n                <li><span class=\"chk chk-orange\"><i class=\"fas fa-check\"></i></span> Department & team access control</li>\n            </ul>\n            <a href=\"/signup?role=transporter\" class=\"btn-for btn-orange\"><i class=\"fas fa-truck\"></i> Register Your Fleet</a>\n        </div>\n    </div>\n</section>\n\n<!-- FEATURES SECTION -->\n<section class=\"section\" id=\"features\">\n    <span class=\"section-label reveal\">Platform Features</span>\n    <h2 class=\"section-title reveal\">Everything You Need</h2>\n    <p class=\"section-subtitle reveal\">A complete logistics management system built specifically for Pakistan's transport industry.</p>\n    <div class=\"features-grid\">\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-map-marked-alt\"></i></div>\n            <div class=\"feature-title\">Live Shipment Tracking</div>\n            <div class=\"feature-desc\">Follow every shipment from pickup to delivery with real-time status updates and location checkpoints.</div>\n        </div>\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-shield-alt\"></i></div>\n            <div class=\"feature-title\">Verified Transporters</div>\n            <div class=\"feature-desc\">All transporters are verified with CNIC, license, and truck documents before they can accept jobs.</div>\n        </div>\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-wallet\"></i></div>\n            <div class=\"feature-title\">Digital Payments (PKR)</div>\n            <div class=\"feature-desc\">Transparent pricing, automatic commission, and digital invoices — all in Pakistani Rupees.</div>\n        </div>\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-sitemap\"></i></div>\n            <div class=\"feature-title\">Organization System</div>\n            <div class=\"feature-desc\">Manage your transport company with departments, team members, and role-based access control.</div>\n        </div>\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-star\"></i></div>\n            <div class=\"feature-title\">Ratings & Reviews</div>\n            <div class=\"feature-desc\">Build trust with a transparent rating system. Top-rated transporters get priority job visibility.</div>\n        </div>\n        <div class=\"feature-card reveal\">\n            <div class=\"feature-icon\"><i class=\"fas fa-robot\"></i></div>\n            <div class=\"feature-title\">AI Assistant</div>\n            <div class=\"feature-desc\">A built-in smart assistant that helps you navigate, place orders, and manage your account naturally.</div>\n        </div>\n    </div>\n</section>\n\n<!-- CTA SECTION -->\n<section class=\"cta-section\">\n    <div class=\"cta-box reveal\">\n        <h2 class=\"cta-title\">Ready to Transform<br><span>Your Logistics?</span></h2>\n        <p class=\"cta-subtitle\">Join Pakistan's growing network of businesses and transporters. Sign up free — no credit card required.</p>\n        <div class=\"cta-buttons\">\n            <a href=\"/signup?role=client\" class=\"btn-hero-primary\"><i class=\"fas fa-box\"></i> I Need Transport</a>\n            <a href=\"/signup?role=transporter\" class=\"btn-hero-secondary\"><i class=\"fas fa-truck\"></i> I'm a Transporter</a>\n        </div>\n    </div>\n</section>\n\n<!-- FOOTER -->\n<footer>\n    <div class=\"footer-top\">\n        <div class=\"footer-brand\">\n            <a href=\"/\" class=\"navbar-logo\" style=\"display:inline-flex;margin-bottom:10px;text-decoration:none;\">\n                <div class=\"logo-icon\"><i class=\"fas fa-truck\"></i></div>\n                <span class=\"navbar-brand\">Digi_TransX</span>\n            </a>\n            <p>Pakistan's smart transport and logistics platform. Connecting clients with trusted transporters since 2026.</p>\n        </div>\n        <div class=\"footer-col\">\n            <h4>Platform</h4>\n            <ul>\n                <li><a href=\"#how-it-works\">How It Works</a></li>\n                <li><a href=\"#features\">Features</a></li>\n                <li><a href=\"#for-who\">For Clients</a></li>\n                <li><a href=\"#for-who\">For Transporters</a></li>\n            </ul>\n        </div>\n        <div class=\"footer-col\">\n            <h4>Company</h4>\n            <ul>\n                      <li><a href=\"\">About Us</a></li>\n                <li><a href=\"\">Contact</a></li>\n                <li><a href=\"\">Partner With Us</a></li>\n                <li><a href=\"\">Help Center</a></li>\n            </ul>\n        </div>\n        <div class=\"footer-col\">\n            <h4>Legal</h4>\n            <ul>\n                <li><a href=\"/frontend/transporter/HTML/Terms/terms.html\">Terms & Conditions</a></li>\n                <li><a href=\"/frontend/transporter/HTML/Privacy/privacy.html\">Privacy Policy</a></li>\n            </ul>\n        </div>\n    </div>\n    <div class=\"footer-bottom\">\n        <p>© 2026 Digi_TransX Transport Services. All rights reserved.</p>\n        <p>Built for <a href=\"#\">Pakistan 🇵🇰</a></p>\n    </div>\n</footer>";

function counter(id, target) {
  const el = document.getElementById(id);
  if (!el) return;

  let val = 0;
  const step = target / (2000 / 16);
  const timer = window.setInterval(() => {
    val += step;
    if (val >= target) {
      val = target;
      window.clearInterval(timer);
    }
    el.textContent = Math.floor(val).toLocaleString();
  }, 16);
}

export default function MainPage() {
  useEffect(() => {
    document.documentElement.dataset.dtxPortal = 'intro';
    document.documentElement.dataset.dtxPage = 'intro-main';
    document.body.dataset.dtxPortal = 'intro';
    document.body.dataset.dtxPage = 'intro-main';

    const fontPreconnect = document.createElement('link');
    fontPreconnect.rel = 'preconnect';
    fontPreconnect.href = 'https://fonts.googleapis.com';
    const fontStylesheet = document.createElement('link');
    fontStylesheet.rel = 'stylesheet';
    fontStylesheet.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap';
    document.head.append(fontPreconnect, fontStylesheet);

    try {
      const key = 'ai_assistant_preferences_v2';
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, JSON.stringify({ mode: 'minimized', backgroundListening: false }));
      }
    } catch {
      // The intro page should render even if browser storage is blocked.
    }

    window.switchTab = (type) => {
      document.querySelectorAll('.how-tab').forEach((tab, index) => {
        tab.classList.toggle('active', (index === 0 && type === 'client') || (index === 1 && type === 'transporter'));
      });
      document.querySelectorAll('.steps-panel').forEach((panel) => panel.classList.remove('active'));
      document.getElementById('panel-' + type)?.classList.add('active');
    };

    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, index) => {
          if (entry.isIntersecting) {
            window.setTimeout(() => entry.target.classList.add('visible'), index * 80);
          }
        });
      },
      { threshold: 0.1 },
    );
    document.querySelectorAll('.reveal').forEach((el) => revealObserver.observe(el));

    const statsObserver = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          counter('s1', 500);
          counter('s2', 12000);
          counter('s3', 35);
          counter('s4', 48);
          statsObserver.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    const statsBar = document.querySelector('.stats-bar');
    if (statsBar) statsObserver.observe(statsBar);

    const updateNavbarShadow = () => {
      const navbar = document.getElementById('navbar');
      if (navbar) {
        navbar.style.boxShadow = window.scrollY > 50 ? '0 4px 12px rgba(0, 0, 0, 0.05)' : 'var(--shadow-medium)';
      }
    };
    window.addEventListener('scroll', updateNavbarShadow);

    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    const toggleMobileNav = () => {
      if (navLinks) {
        navLinks.style.display = navLinks.style.display === 'flex' ? 'none' : 'flex';
      }
    };
    hamburger?.addEventListener('click', toggleMobileNav);

    return () => {
      revealObserver.disconnect();
      statsObserver.disconnect();
      window.removeEventListener('scroll', updateNavbarShadow);
      hamburger?.removeEventListener('click', toggleMobileNav);
      delete window.switchTab;
      document.head.removeChild(fontPreconnect);
      document.head.removeChild(fontStylesheet);
      delete document.documentElement.dataset.dtxPortal;
      delete document.documentElement.dataset.dtxPage;
      delete document.body.dataset.dtxPortal;
      delete document.body.dataset.dtxPage;
    };
  }, []);

  return <div dangerouslySetInnerHTML={{ __html: mainPageHtml }} />;
}
