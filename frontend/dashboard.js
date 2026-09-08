async function load(){

let r =
await fetch("/signals");


let data =
await r.json();


let table =
document.getElementById("data");


table.innerHTML="";


data.forEach(x=>{


table.innerHTML += `

<tr>

<td>${x[1]}</td>

<td>${x[2]}</td>

<td>${x[3]}</td>

</tr>

`;

});


}


load();


setInterval(
load,
10000
);
