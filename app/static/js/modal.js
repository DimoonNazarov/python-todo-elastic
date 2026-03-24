const modal = document.querySelector("#exampleModal");
const modalTitle = modal.querySelector("#exampleModalTitle");
const defaultModalTitle = "Вы уверены?";

const closeShowModal = (action, titleText = defaultModalTitle) => {
    if (modal.classList.contains("show")) {
        modal.classList.remove('show')
        setTimeout(() => {
            modal.style = "display: none;";
            modalTitle.textContent = defaultModalTitle;
            const confirmButton = modal.querySelector("button.btn.btn-success");
            if (confirmButton) {
                confirmButton.remove();
            }
        }, 0)
    } else {
        modalTitle.textContent = titleText;
        addActionButton(action);
        modal.style = "display: block; background-color: rgba(0,0,0,0.5)";
        setTimeout(() => {
            modal.classList.add("show");
        }, 0)
    }
}

const addActionButton = (action) => {
    const button = document.createElement("button");

    button.classList.add("btn", "btn-success");
    button.textContent = 'Да'

    button.addEventListener("click", () => {
        action()
        closeShowModal()
    })

    modal.querySelector(".modal-footer").appendChild(button);
}

modal.querySelectorAll('[data-bs-dismiss="modal"]').forEach((button) => {
    button.addEventListener("click", () => closeShowModal())
})
