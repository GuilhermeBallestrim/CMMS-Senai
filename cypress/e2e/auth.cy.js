describe("Autenticação (login/logout)", () => {
  const adminEmail = Cypress.env("ADMIN_EMAIL") || "admin@senai.br";
  const adminPassword = Cypress.env("ADMIN_PASSWORD") || "Admin@123456";

  beforeEach(() => {
    cy.uiLogout().then(() => {
      // Ignora se já não estiver logado (404 na rota de logout não bloqueia).
    });
  });

  it("faz login com credenciais de administrador e acessa o dashboard", () => {
    cy.uiLogin(adminEmail, adminPassword);
    cy.contains("h1", "Dashboard").should("be.visible");
    cy.get(".profile__info strong").should("contain.text", "Administrador");
  });

  it("rejeita credenciais inválidas e exibe mensagem de erro", () => {
    cy.visit("/login");
    cy.get('input[name="email"]').type("inexistente@senai.br");
    cy.get('input[name="password"]').type("senha_errada");
    cy.get('button[type="submit"]').contains("ENTRAR").click();
    cy.contains("E-mail ou senha inválidos").should("be.visible");
    cy.url().should("include", "/login");
  });

  it("faz logout e retorna para a página de login", () => {
    cy.uiLogin(adminEmail, adminPassword);
    cy.uiLogout();
    cy.contains("h1", "Bem-vindo de volta").should("be.visible");
  });
});
