// The project is configured and the Pages hostname is authorized.
document.documentElement.dataset.eslMembershipConfigured = "true";
for (const link of document.querySelectorAll("[data-esl-membership-link]")) {
  link.hidden = false;
}
